# --- Observability: single-pane CloudWatch dashboard + saved Logs Insights queries ---
# Lives at: CloudWatch > Dashboards > ${var.project}-mlfinops   (region ${var.region})
# Uses metrics that exist with zero extra config (AWS/Lambda + AWS/ApiGateway for the
# HTTP API). The handler's structured JSON logs feed the saved queries below.

locals {
  api_id = aws_apigatewayv2_api.api.id
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project}-mlfinops"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Lambda — Invocations / Errors / Throttles"
          region  = var.region
          view    = "timeSeries"
          stacked = false
          period  = 60
          stat    = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.lambda_name],
            ["AWS/Lambda", "Errors", "FunctionName", var.lambda_name],
            ["AWS/Lambda", "Throttles", "FunctionName", var.lambda_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda — Duration (ms)"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_name, { stat = "p50", label = "p50" }],
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_name, { stat = "p99", label = "p99" }],
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_name, { stat = "Average", label = "avg" }],
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_name, { stat = "Maximum", label = "max" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Lambda — Concurrent executions"
          region = var.region
          view   = "timeSeries"
          period = 60
          stat   = "Maximum"
          metrics = [
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", var.lambda_name]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "API Gateway — Request count & errors"
          region = var.region
          view   = "timeSeries"
          period = 60
          stat   = "Sum"
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", local.api_id, { label = "requests" }],
            ["AWS/ApiGateway", "4xx", "ApiId", local.api_id, { label = "4xx" }],
            ["AWS/ApiGateway", "5xx", "ApiId", local.api_id, { label = "5xx" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "API Gateway — Latency (ms)"
          region = var.region
          view   = "timeSeries"
          period = 60
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiId", local.api_id, { stat = "p50", label = "total p50" }],
            ["AWS/ApiGateway", "Latency", "ApiId", local.api_id, { stat = "p99", label = "total p99" }],
            ["AWS/ApiGateway", "IntegrationLatency", "ApiId", local.api_id, { stat = "p99", label = "integration p99" }]
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Lambda — Cost drivers (billed duration ms, Sum)"
          region = var.region
          view   = "singleValue"
          period = 86400
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.lambda_name, { stat = "Sum", label = "invocations (24h)" }],
            ["AWS/Lambda", "Duration", "FunctionName", var.lambda_name, { stat = "Sum", label = "total duration ms (24h)" }]
          ]
        }
      }
    ]
  })
}

# --- Saved Logs Insights queries (CloudWatch > Logs Insights > Saved queries) ---
# The handler emits JSON, so these fields are auto-discovered — no parse step needed.

resource "aws_cloudwatch_query_definition" "latency" {
  name            = "${var.project}-mlfinops/latency-percentiles-by-coldstart"
  log_group_names = [aws_cloudwatch_log_group.lambda.name]

  query_string = <<-EOT
    filter event = "inference"
    | stats count(*) as n, avg(latency_ms) as avg_ms, pct(latency_ms, 50) as p50_ms, pct(latency_ms, 99) as p99_ms by cold_start
  EOT
}

resource "aws_cloudwatch_query_definition" "predictions" {
  name            = "${var.project}-mlfinops/predictions-breakdown"
  log_group_names = [aws_cloudwatch_log_group.lambda.name]

  query_string = <<-EOT
    filter event = "inference"
    | stats count(*) as n by prediction
  EOT
}

resource "aws_cloudwatch_query_definition" "errors" {
  name            = "${var.project}-mlfinops/recent-errors"
  log_group_names = [aws_cloudwatch_log_group.lambda.name]

  query_string = <<-EOT
    filter event = "inference_error"
    | fields @timestamp, request_id, error, latency_ms
    | sort @timestamp desc
    | limit 50
  EOT
}
