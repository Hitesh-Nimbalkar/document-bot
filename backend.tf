
terraform {
  backend "s3" {
    bucket         = "msumani-terraform-state"
    key            = "chat-document-v2.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "msumani-terraform-lock"
    encrypt        = true
  }
}



