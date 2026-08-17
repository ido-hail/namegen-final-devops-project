terraform {
  backend "s3" {
    key          = "namegen/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
