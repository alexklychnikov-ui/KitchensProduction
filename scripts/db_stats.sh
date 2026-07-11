#!/bin/bash
for t in catalog_items orders faq_items leads dialogs app_settings product_classes escalation_rules service_fees countertop_materials; do
  c=$(docker exec kitchens-postgres psql -U kitchens -d kitchens_bot -t -A -c "SELECT count(*) FROM $t")
  echo "$t: $c"
done
