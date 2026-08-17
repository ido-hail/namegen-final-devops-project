variable "name_prefix" {
  description = "Prefix used for network resource names."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block assigned to the VPC."
  type        = string
}

variable "public_subnet_cidrs" {
  description = "IPv4 CIDR blocks assigned to the two public subnets."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) == 2
    error_message = "Exactly two public subnet CIDR blocks are required."
  }
}

variable "availability_zones" {
  description = "Two Availability Zones in which the public subnets are created."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2
    error_message = "Exactly two Availability Zones are required."
  }
}
