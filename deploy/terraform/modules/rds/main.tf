# RDS PostgreSQL Module for GALILEO Platform
# Production-grade PostgreSQL with HA, backups, and monitoring

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

# Generate random password if not provided
resource "random_password" "master" {
  count   = var.master_password == null ? 1 : 0
  length  = 32
  special = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

locals {
  master_password = var.master_password != null ? var.master_password : random_password.master[0].result
}

# Store password in AWS Secrets Manager
resource "aws_secretsmanager_secret" "rds_password" {
  name                    = "${var.identifier}-master-password"
  description             = "Master password for ${var.identifier} RDS instance"
  recovery_window_in_days = var.secret_recovery_window_days

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "rds_password" {
  secret_id = aws_secretsmanager_secret.rds_password.id
  secret_string = jsonencode({
    username = var.master_username
    password = local.master_password
    engine   = "postgres"
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
    dbname   = var.database_name
  })
}

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name        = "${var.identifier}-subnet-group"
  description = "DB subnet group for ${var.identifier}"
  subnet_ids  = var.subnet_ids

  tags = merge(
    var.tags,
    {
      Name = "${var.identifier}-subnet-group"
    }
  )
}

# DB Security Group
resource "aws_security_group" "rds" {
  name        = "${var.identifier}-sg"
  description = "Security group for ${var.identifier} RDS instance"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL from allowed security groups"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_groups
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(
    var.tags,
    {
      Name = "${var.identifier}-sg"
    }
  )
}

# DB Parameter Group
resource "aws_db_parameter_group" "main" {
  name        = "${var.identifier}-params"
  family      = var.parameter_group_family
  description = "Parameter group for ${var.identifier}"

  # Logging
  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000"  # Log queries > 1 second
  }

  # Connection settings
  parameter {
    name         = "max_connections"
    value        = var.max_connections
    apply_method = "pending-reboot"
  }

  # Performance settings
  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements,timescaledb,auto_explain"
    apply_method = "pending-reboot"
  }

  parameter {
    name  = "auto_explain.log_min_duration"
    value = "5000"
  }

  parameter {
    name  = "track_io_timing"
    value = "on"
  }

  tags = var.tags
}

# KMS Key for encryption
resource "aws_kms_key" "rds" {
  description             = "KMS key for ${var.identifier} encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(
    var.tags,
    {
      Name = "${var.identifier}-kms"
    }
  )
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.identifier}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

# IAM Role for Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  count = var.monitoring_interval > 0 ? 1 : 0

  name = "${var.identifier}-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "monitoring.rds.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  count      = var.monitoring_interval > 0 ? 1 : 0
  role       = aws_iam_role.rds_monitoring[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

# Primary DB Instance
resource "aws_db_instance" "main" {
  identifier = var.identifier

  # Engine
  engine               = "postgres"
  engine_version       = var.engine_version
  instance_class       = var.instance_class
  allocated_storage    = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type         = var.storage_type
  storage_encrypted    = true
  kms_key_id           = aws_kms_key.rds.arn
  iops                 = var.storage_type == "io1" || var.storage_type == "io2" ? var.iops : null

  # Database
  db_name  = var.database_name
  username = var.master_username
  password = local.master_password
  port     = 5432

  # Network
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = var.multi_az

  # Backup
  backup_retention_period = var.backup_retention_period
  backup_window          = var.backup_window
  copy_tags_to_snapshot  = true
  delete_automated_backups = false

  # Maintenance
  maintenance_window         = var.maintenance_window
  auto_minor_version_upgrade = var.auto_minor_version_upgrade

  # Parameter group
  parameter_group_name = aws_db_parameter_group.main.name

  # Performance Insights
  performance_insights_enabled          = var.performance_insights_enabled
  performance_insights_retention_period = var.performance_insights_retention_period
  performance_insights_kms_key_id       = aws_kms_key.rds.arn

  # Enhanced Monitoring
  monitoring_interval = var.monitoring_interval
  monitoring_role_arn = var.monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null

  # CloudWatch Logs
  enabled_cloudwatch_logs_exports = var.enabled_cloudwatch_logs_exports

  # Deletion Protection
  deletion_protection      = var.deletion_protection
  skip_final_snapshot      = !var.deletion_protection
  final_snapshot_identifier = var.deletion_protection ? "${var.identifier}-final-${formatdate("YYYYMMDDhhmmss", timestamp())}" : null

  apply_immediately = var.apply_immediately

  tags = merge(
    var.tags,
    {
      Name = var.identifier
    }
  )

  lifecycle {
    ignore_changes = [
      final_snapshot_identifier,
      password,
    ]
  }
}

# Read Replicas
resource "aws_db_instance" "read_replica" {
  count = var.create_read_replica ? var.read_replica_count : 0

  identifier             = "${var.identifier}-read-${count.index + 1}"
  replicate_source_db    = aws_db_instance.main.identifier
  instance_class         = var.read_replica_instance_class != null ? var.read_replica_instance_class : var.instance_class
  publicly_accessible    = false
  auto_minor_version_upgrade = var.auto_minor_version_upgrade

  vpc_security_group_ids = [aws_security_group.rds.id]

  # Performance Insights for replicas
  performance_insights_enabled = var.performance_insights_enabled
  performance_insights_kms_key_id = aws_kms_key.rds.arn

  # Enhanced Monitoring
  monitoring_interval = var.monitoring_interval
  monitoring_role_arn = var.monitoring_interval > 0 ? aws_iam_role.rds_monitoring[0].arn : null

  skip_final_snapshot = true

  tags = merge(
    var.tags,
    {
      Name = "${var.identifier}-read-${count.index + 1}"
      Role = "read-replica"
    }
  )

  depends_on = [aws_db_instance.main]
}

# CloudWatch Alarms
resource "aws_cloudwatch_metric_alarm" "cpu_utilization" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.identifier}-cpu-utilization-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "80"
  alarm_description   = "RDS instance CPU utilization is high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "free_storage_space" {
  count = var.enable_alarms ? 1 : 0

  alarm_name          = "${var.identifier}-free-storage-space-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "10737418240"  # 10 GB in bytes
  alarm_description   = "RDS instance free storage space is low"
  alarm_actions       = var.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "replica_lag" {
  count = var.create_read_replica && var.enable_alarms ? var.read_replica_count : 0

  alarm_name          = "${var.identifier}-read-${count.index + 1}-replica-lag-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ReplicaLag"
  namespace           = "AWS/RDS"
  period              = "300"
  statistic           = "Average"
  threshold           = "30"  # 30 seconds
  alarm_description   = "RDS read replica lag is high"
  alarm_actions       = var.alarm_actions

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.read_replica[count.index].id
  }

  tags = var.tags
}
