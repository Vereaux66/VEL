# VEL Trading Platform - DNS and SSL Configuration
# Manages Route53 records and ACM certificates for VEL

data "aws_route53_zone" "vel_zone" {
  name         = var.vel_dns_zone
  private_zone = false
}

resource "aws_acm_certificate" "vel_tls" {
  domain_name               = var.vel_dns_zone
  subject_alternative_names = ["*.${var.vel_dns_zone}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Component = "VEL-Security"
  }
}

resource "aws_route53_record" "vel_cert_validation" {
  for_each = {
    for validation in aws_acm_certificate.vel_tls.domain_validation_options :
    validation.domain_name => {
      record_name  = validation.resource_record_name
      record_type  = validation.resource_record_type
      record_value = validation.resource_record_value
    }
  }

  zone_id = data.aws_route53_zone.vel_zone.zone_id
  name    = each.value.record_name
  type    = each.value.record_type
  records = [each.value.record_value]
  ttl     = 60

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "vel_tls_validated" {
  certificate_arn         = aws_acm_certificate.vel_tls.arn
  validation_record_fqdns = [for record in aws_route53_record.vel_cert_validation : record.fqdn]
}
