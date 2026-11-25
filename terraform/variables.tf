variable "region" {
  description = "AWS region for all resources (Ohio)."
  type        = string
  default     = "us-east-2"
}

variable "project" {
  description = "Cost-allocation tag value applied to every resource."
  type        = string
  default     = "capstone"
}

variable "lambda_name" {
  description = "Name of the inference Lambda function."
  type        = string
  default     = "hof-inference"
}
