output "id" {
  description = "RDS instance ID"
  value       = aws_db_instance.main.id
}

output "arn" {
  description = "RDS instance ARN"
  value       = aws_db_instance.main.arn
}

output "endpoint" {
  description = "RDS instance endpoint (host:port)"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "address" {
  description = "RDS instance hostname"
  value       = aws_db_instance.main.address
  sensitive   = true
}

output "port" {
  description = "RDS instance port"
  value       = aws_db_instance.main.port
}

output "database_name" {
  description = "Database name"
  value       = aws_db_instance.main.db_name
}

output "username" {
  description = "Master username"
  value       = aws_db_instance.main.username
  sensitive   = true
}

output "password_secret_arn" {
  description = "ARN of Secrets Manager secret containing password"
  value       = aws_secretsmanager_secret.rds_password.arn
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.rds.id
}

output "read_replica_endpoints" {
  description = "Read replica endpoints"
  value       = aws_db_instance.read_replica[*].endpoint
  sensitive   = true
}

output "kms_key_arn" {
  description = "KMS key ARN for encryption"
  value       = aws_kms_key.rds.arn
}
