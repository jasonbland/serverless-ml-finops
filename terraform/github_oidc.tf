# --- GitHub Actions OIDC: lets CI assume a scoped IAM role with NO stored AWS keys ---

variable "github_repo" {
  description = "owner/repo allowed to assume the CI role."
  type        = string
  default     = "jasonbland/serverless-ml-finops"
}

# Fetch GitHub's OIDC cert chain so we can pin the root thumbprint.
data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[length(data.tls_certificate.github.certificates) - 1].sha1_fingerprint]
}

# Role that only this repo's workflows can assume (via web identity).
resource "aws_iam_role" "github_ci" {
  name = "${var.project}-github-ci"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      # AWS requires the sub (or job_workflow_ref) to be constrained — aud/repository alone
      # is rejected as "scoped to all". GitHub now issues an IMMUTABLE sub with numeric IDs:
      #   repo:<owner>@<ownerID>/<repo>@<repoID>:<ref...>
      # so the @* wildcards absorb the IDs while the literal owner/repo names scope the trust
      # to exactly this repository (any ref).
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${split("/", var.github_repo)[0]}@*/${split("/", var.github_repo)[1]}@*:*"
        }
      }
    }]
  })
}

# Least-privilege: Cost Explorer read (cost_query.py) + CloudWatch metric read
# (metrics_summary.py). GetMetricData is namespace-agnostic, so this one grant covers
# both the AWS/Lambda and AWS/ApiGateway metrics the summary reads.
resource "aws_iam_role_policy" "github_ci_ce" {
  name = "finops-read"
  role = aws_iam_role.github_ci.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ce:GetCostAndUsage",
        "ce:GetCostAndUsageWithResources",
        "ce:GetDimensionValues",
        "ce:GetTags",
        "cloudwatch:GetMetricData",
        "cloudwatch:ListMetrics",
      ]
      Resource = "*"
    }]
  })
}

output "github_ci_role_arn" {
  description = "Set this as the repo Actions variable AWS_ROLE_ARN."
  value       = aws_iam_role.github_ci.arn
}
