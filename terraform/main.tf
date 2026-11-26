terraform {
  required_version = ">= 1.5"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
    tls     = { source = "hashicorp/tls", version = "~> 4.0" }
  }
}

# Every resource gets Project=<project> via default_tags → cost-allocation attribution.
provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = var.project }
  }
}

data "aws_caller_identity" "me" {}

# --- Package the Lambda: handler + the exported model params (pure-Python, no deps) ---
data "archive_file" "lambda" {
  type        = "zip"
  output_path = "${path.module}/lambda.zip"

  source {
    content  = file("${path.module}/../src/inference/handler.py")
    filename = "handler.py"
  }
  source {
    content  = file("${path.module}/../src/train/model_params.json")
    filename = "model_params.json"
  }
}

# --- S3 bucket for the model artifact (versioned: supports the Phase 4 versioning story) ---
resource "aws_s3_bucket" "model" {
  bucket = "${var.project}-mlfinops-model-${data.aws_caller_identity.me.account_id}"
}

resource "aws_s3_bucket_versioning" "model" {
  bucket = aws_s3_bucket.model.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_object" "model_params" {
  bucket = aws_s3_bucket.model.id
  key    = "model_params.json"
  source = "${path.module}/../src/train/model_params.json"
  etag   = filemd5("${path.module}/../src/train/model_params.json")
}

# --- IAM execution role (least privilege: just CloudWatch Logs) ---
resource "aws_iam_role" "lambda" {
  name = "${var.lambda_name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- CloudWatch log group (explicit so it is tagged + retention-bounded) ---
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.lambda_name}"
  retention_in_days = 14
}

# --- Lambda ---
resource "aws_lambda_function" "infer" {
  function_name    = var.lambda_name
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 10
  memory_size      = 128
  depends_on       = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy_attachment.basic]
}

# --- API Gateway HTTP API → Lambda (POST /predict) ---
resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project}-mlfinops-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.infer.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "predict" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /predict"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.infer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
