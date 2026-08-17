output "vpc_id" {
  description = "ID of the NameGen VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "IDs of the two public subnets."
  value = [
    for key in sort(keys(aws_subnet.public)) :
    aws_subnet.public[key].id
  ]
}

output "availability_zones" {
  description = "Availability Zones used by the public subnets."
  value = [
    for key in sort(keys(aws_subnet.public)) :
    aws_subnet.public[key].availability_zone
  ]
}

output "public_route_table_id" {
  description = "ID of the public route table."
  value       = aws_route_table.public.id
}
