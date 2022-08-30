
variable "analytics_instance_capacity_capacity_type" {
  default = "OLPU_COUNT"
}

variable "analytics_instance_capacity_capacity_value" {
  default = 4
}

variable "analytics_instance_feature_set" {
  default = "ENTERPRISE_ANALYTICS"
}

variable "analytics_instance_license_type" {
  default = "LICENSE_INCLUDED"
}

variable "analytics_instance_name" {
  default = "OAC"
}

variable "analytics_instance_idcs_access_token" {}


resource "oci_analytics_analytics_instance" "oac_instance" {
    #Required
    capacity {
        #Required
        capacity_type = var.analytics_instance_capacity_capacity_type
        capacity_value = var.analytics_instance_capacity_capacity_value
    }
    compartment_id = var.compartment_ocid
    feature_set = var.analytics_instance_feature_set
    idcs_access_token = var.analytics_instance_idcs_access_token
    license_type = var.analytics_instance_license_type
    name = var.analytics_instance_name

    #Optional
    description = "OAC Instance"
    freeform_tags = {"Project"= "RedBull"}
}