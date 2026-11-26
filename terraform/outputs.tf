output "api_url" {
  description = "POST feature JSON here to get a prediction."
  value       = "${aws_apigatewayv2_api.api.api_endpoint}/predict"
}

output "lambda_name" {
  value = aws_lambda_function.infer.function_name
}

output "model_bucket" {
  value = aws_s3_bucket.model.bucket
}

output "dashboard_url" {
  description = "Single-pane CloudWatch dashboard (watch the load test live)."
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards/dashboard/${aws_cloudwatch_dashboard.main.dashboard_name}"
}
