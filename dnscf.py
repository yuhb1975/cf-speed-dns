#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudflare DNS updater.
Updates Cloudflare DNS records with the latest optimized IPs.
"""

import json
import traceback
from typing import List, Dict, Any

import requests

from common import (
    get_env_var,
    get_cf_speed_test_ip,
    pushplus_send,
    format_current_time,
    log_success,
    log_error,
    DEFAULT_TIMEOUT,
)

# API Configuration
CF_API_BASE = "https://api.cloudflare.com/client/v4"


def get_headers() -> Dict[str, str]:
    """Build request headers with authentication."""
    token = get_env_var("CF_API_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def get_zone_id() -> str:
    """Get Cloudflare zone ID from environment."""
    return get_env_var("CF_ZONE_ID")


def get_dns_records(name: str, zone_id: str, headers: Dict[str, str]) -> List[str]:
    """
    Fetch DNS record IDs for the given name.

    Args:
        name: DNS record name
        zone_id: Cloudflare zone ID
        headers: Request headers with auth

    Returns:
        List of record IDs
    """
    record_ids = []
    url = f"{CF_API_BASE}/zones/{zone_id}/dns_records"

    try:
        response = requests.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        records = response.json().get("result", [])

        for record in records:
            if record.get("name") == name and record.get("type") == "A":
                record_ids.append(record.get("id"))
    except requests.RequestException as e:
        print(f"Error fetching DNS records: {e}")
    except Exception as e:
        traceback.print_exc()
        print(f"Unexpected error fetching DNS records: {e}")

    return record_ids


def update_dns_record(
    record_id: str,
    name: str,
    cf_ip: str,
    zone_id: str,
    headers: Dict[str, str]
) -> str:
    """
    Update a DNS record with the new IP.

    Args:
        record_id: DNS record ID
        name: DNS record name
        cf_ip: New IP address
        zone_id: Cloudflare zone ID
        headers: Request headers with auth

    Returns:
        Status message
    """
    url = f"{CF_API_BASE}/zones/{zone_id}/dns_records/{record_id}"
    data = {
        "type": "A",
        "name": name,
        "content": cf_ip,
        "ttl": 1  # 1 means automatic (use Cloudflare default)
    }

    try:
        response = requests.put(url, headers=headers, json=data, timeout=DEFAULT_TIMEOUT)
        if not response.ok:
            # Print detailed error for debugging
            print(f"API Error: {response.status_code} - {response.text}")
        response.raise_for_status()
        log_success("cf_dns_change", cf_ip)
        return f"ip:{cf_ip} 解析 {name} 成功"
    except requests.RequestException as e:
        traceback.print_exc()
        log_error("cf_dns_change", str(e))
        return f"ip:{cf_ip} 解析 {name} 失败"


def main() -> None:
    """Main entry point."""
    # Load configuration
    cf_zone_id = get_zone_id()
    cf_dns_name = get_env_var("CF_DNS_NAME")
    pushplus_token = get_env_var("PUSHPLUS_TOKEN")

    headers = get_headers()

    # Fetch latest optimized IPs
    ip_addresses_str = get_cf_speed_test_ip()
    if not ip_addresses_str:
        log_error("get_cf_speed_test_ip", "Failed to fetch IP addresses")
        return

    ip_addresses = [ip.strip() for ip in ip_addresses_str.split(",") if ip.strip()]
    if not ip_addresses:
        log_error("parse_ip_addresses", "No valid IP addresses found")
        return

    # Get existing DNS records
    dns_records = get_dns_records(cf_dns_name, cf_zone_id, headers)
    if not dns_records:
        log_error("get_dns_records", f"No DNS records found for {cf_dns_name}")
        return

    # Update DNS records and collect results
    pushplus_content = []
    for index, ip_address in enumerate(ip_addresses):
        if index >= len(dns_records):
            break
        result = update_dns_record(
            dns_records[index],
            cf_dns_name,
            ip_address,
            cf_zone_id,
            headers
        )
        pushplus_content.append(result)

    # Send notification
    if pushplus_content:
        pushplus_send(pushplus_token, "IP优选DNSCF推送", "\n".join(pushplus_content))


if __name__ == "__main__":
    main()
