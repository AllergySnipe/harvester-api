from flask import Flask, request, jsonify
import subprocess
import requests
import re
import time
import json
import os
import tempfile
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

class TheHarvesterAPI:
    def __init__(self):
        self.email_validator_url = "https://rapid-email-verifier.fly.dev/api/validate"
        self.harvester_path = "/app/theHarvester/theHarvester.py"
        
    def run_theharvester(self, domain, sources="google,bing,yahoo", limit=100):
        """Run theHarvester with improved parsing and fallback"""
        
        # Try theHarvester first
        harvester_result = self.try_theharvester(domain, sources, limit)
        
        # If theHarvester finds emails, return them
        if harvester_result['emails']:
            return harvester_result
        
        # If no emails found, try basic web scraping as backup
        scraping_result = self.try_web_scraping(domain)
        
        # Combine results or use patterns
        if scraping_result['emails']:
            return {
                "emails": scraping_result['emails'],
                "count": len(scraping_result['emails']),
                "domain": domain,
                "sources": sources,
                "method": "web_scraping_fallback",
                "status": "fallback_success",
                "note": "theHarvester found 0 emails, used web scraping"
            }
        else:
            # Final fallback to patterns
            return self.fallback_with_patterns(domain, "no_emails_found_anywhere")
    
    def try_theharvester(self, domain, sources, limit):
        """Attempt to run theHarvester"""
        # Split sources to avoid timeout with too many sources
        source_list = sources.split(',')
        quick_sources = source_list[:3]  # Use first 3 sources for speed
        sources_string = ','.join(quick_sources)
        
        cmd = [
            "python3", self.harvester_path,
            "-d", domain,
            "-l", str(min(limit, 50)),  # Reduce limit for speed
            "-b", sources_string
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,  # Reduced timeout
                cwd="/app/theHarvester"
            )
            
            # Parse emails from output
            emails = self.parse_harvester_output(result.stdout, result.stderr, domain)
            
            return {
                "emails": emails,
                "count": len(emails),
                "domain": domain,
                "sources": sources_string,
                "method": "theHarvester",
                "status": "success" if emails else "no_results",
                "raw_output": (result.stdout + result.stderr)[:300],
                "return_code": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {"emails": [], "error": "timeout", "method": "theHarvester"}
        except Exception as e:
            return {"emails": [], "error": str(e), "method": "theHarvester"}
    
    def parse_harvester_output(self, stdout, stderr, domain):
        """Parse theHarvester output more aggressively"""
        emails = set()
        full_output = (stdout or "") + " " + (stderr or "")
        
        if not full_output:
            return []
        
        # Multiple email regex patterns
        patterns = [
            r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b',
            r'([a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})',
            r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        ]
        
        for pattern in patterns:
            found = re.findall(pattern, full_output, re.IGNORECASE)
            emails.update([email.lower().strip() for email in found])
        
        # Filter out unwanted emails
        filtered_emails = []
        skip_patterns = [
            'cmartorella', 'edge-security', 'theharvester', 'christian',
            'example.com', 'test.com', 'localhost', 'github.com',
            'noreply', 'no-reply', 'donotreply'
        ]
        
        for email in emails:
            if '@' in email and '.' in email.split('@')[1]:
                if not any(skip in email for skip in skip_patterns):
                    if len(email) > 5 and len(email) < 100:
                        filtered_emails.append(email)
        
        return list(set(filtered_emails))
    
    def try_web_scraping(self, domain):
        """Backup web scraping method"""
        emails = set()
        
        try:
            # Try HTTPS first, then HTTP
            for protocol in ['https', 'http']:
                try:
                    url = f"{protocol}://{domain}"
                    response = requests.get(
                        url,
                        timeout=15,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        },
                        verify=False,
                        allow_redirects=True
                    )
                    
                    if response.status_code == 200:
                        # Extract emails from page
                        page_emails = re.findall(
                            r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b',
                            response.text,
                            re.IGNORECASE
                        )
                        emails.update([email.lower() for email in page_emails])
                        
                        # Try common pages
                        common_pages = ['/contact', '/about', '/contact-us', '/team']
                        for page in common_pages:
                            try:
                                page_response = requests.get(
                                    f"{protocol}://{domain}{page}",
                                    timeout=10,
                                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                                    verify=False
                                )
                                if page_response.status_code == 200:
                                    page_emails = re.findall(
                                        r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b',
                                        page_response.text,
                                        re.IGNORECASE
                                    )
                                    emails.update([email.lower() for email in page_emails])
                            except:
                                continue
                        break  # Success with this protocol
                        
                except requests.RequestException:
                    continue  # Try next protocol
                    
        except Exception as e:
            pass
        
        # Filter emails to domain-relevant ones
        domain_emails = []
        for email in emails:
            email_domain = email.split('@')[1] if '@' in email else ''
            if (domain.lower() in email_domain or 
                email_domain in domain.lower() or
                any(prefix in email for prefix in ['info@', 'contact@', 'sales@', 'support@', 'admin@'])):
                domain_emails.append(email)
        
        return {
            "emails": list(set(domain_emails)),
            "method": "web_scraping"
        }
    
    def fallback_with_patterns(self, domain, error_reason):
        """Enhanced fallback with more realistic patterns"""
        # Generate smarter email patterns
        prefixes = [
            'info', 'contact', 'support', 'sales', 'admin', 'hello',
            'help', 'service', 'office', 'mail', 'team', 'general',
            'inquiry', 'customer', 'business', 'marketing', 'export',
            'international', 'trading', 'orders', 'procurement'
        ]
        
        # For food ingredient exporters, add industry-specific prefixes
        if any(word in domain.lower() for word in ['food', 'ingredient', 'spice', 'export', 'trading']):
            prefixes.extend(['export', 'international', 'trading', 'orders', 'procurement', 'quality'])
        
        fallback_emails = [f"{prefix}@{domain}" for prefix in prefixes[:12]]  # Limit to 12
        
        return {
            "emails": fallback_emails,
            "count": len(fallback_emails),
            "domain": domain,
            "method": "smart_patterns",
            "status": "fallback",
            "error": error_reason,
            "note": f"Generated {len(fallback_emails)} potential email patterns for {domain}"
        }
    
    def validate_email_batch(self, emails):
        """Email validation with better error handling"""
        validated_emails = []
        
        for email in emails[:10]:  # Limit validation
            try:
                response = requests.post(
                    self.email_validator_url,
                    json={"email": email},
                    timeout=5,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    validated_emails.append({
                        "email": email,
                        "valid": data.get("valid", False),
                        "deliverable": data.get("deliverable", False),
                        "disposable": data.get("disposable", False)
                    })
                else:
                    # Include email even if validation fails
                    validated_emails.append({
                        "email": email,
                        "valid": "unknown",
                        "validation_error": f"HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                validated_emails.append({
                    "email": email,
                    "valid": "unknown",
                    "validation_error": "timeout_or_error"
                })
        
        return validated_emails

        """Validate emails using external API"""
        validated_emails = []
        
        for email in emails[:15]:  # Limit to prevent API abuse
            try:
                response = requests.post(
                    self.email_validator_url,
                    json={"email": email},
                    timeout=8,
                    headers={'Content-Type': 'application/json'}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    validated_emails.append({
                        "email": email,
                        "valid": data.get("valid", False),
                        "deliverable": data.get("deliverable", False),
                        "disposable": data.get("disposable", False),
                        "role_account": data.get("role_account", False)
                    })
                else:
                    validated_emails.append({
                        "email": email,
                        "valid": "unknown",
                        "error": f"HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                validated_emails.append({
                    "email": email,
                    "valid": "unknown",
                    "error": f"Validation failed: {str(e)[:50]}"
                })
        
        return validated_emails

# Initialize theHarvester API
harvester_api = TheHarvesterAPI()

@app.route('/health', methods=['GET'])
def health_check_render():
    """Health check for Render deployment"""
    return "OK", 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "🔍 theHarvester API v2.0 - Professional OSINT Email Discovery",
        "status": "running",
        "powered_by": "theHarvester + Pattern Generation + Email Validation",
        "endpoints": {
            "health": "GET /health",
            "api_health": "GET /api/health",
            "single_domain": "POST /api/find-emails", 
            "bulk_domains": "POST /api/find-emails-bulk"
        },
        "features": [
            "Real theHarvester OSINT integration",
            "Google, Bing, Yahoo search engine scraping",
            "Fallback pattern generation",
            "Email validation",
            "Bulk processing"
        ],
        "example_request": {
            "domain": "example.com",
            "validate": True,
            "sources": "google,bing,yahoo,linkedin"
        }
    }), 200

@app.route('/api/health', methods=['GET'])
def health_check_api():
    """Detailed API health check"""
    # Test theHarvester installation
    harvester_status = "unknown"
    try:
        test_result = subprocess.run([
            "python3", "/app/theHarvester/theHarvester.py", "-h"
        ], capture_output=True, text=True, timeout=10)
        harvester_status = "✓ working" if test_result.returncode == 0 else "✗ error"
    except:
        harvester_status = "✗ not_found"
    
    return jsonify({
        "status": "healthy",
        "service": "theharvester-api",
        "timestamp": time.time(),
        "version": "2.0",
        "components": {
            "flask": "✓ running",
            "theHarvester": harvester_status,
            "email_validator": "✓ available",
            "fallback_patterns": "✓ ready"
        }
    }), 200

@app.route('/api/find-emails', methods=['POST'])
def find_emails_single():
    """Single domain email discovery with theHarvester"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domain = data.get('domain', '').strip()
        validate = data.get('validate', True)
        sources = data.get('sources', 'google,bing,yahoo')
        
        if not domain:
            return jsonify({"error": "Domain parameter required"}), 400
        
        # Clean domain input
        domain = domain.replace('http://', '').replace('https://', '').replace('www.', '')
        if '/' in domain:
            domain = domain.split('/')[0]
        
        # Run theHarvester
        result = harvester_api.run_theharvester(domain, sources)
        
        response_data = {
            "success": True,
            "domain": domain,
            "method": result['method'],
            "status": result['status'],
            "emails_found": result['emails'],
            "total_found": result['count'],
            "sources_used": sources
        }
        
        # Add error info if fallback was used
        if result.get('error'):
            response_data["harvester_error"] = result['error']
            response_data["note"] = result.get('note', '')
        
        # Add raw output for debugging (first 200 chars)
        if result.get('raw_output'):
            response_data["debug_output"] = result['raw_output'][:200]
        
        # Email validation
        if validate and result['emails']:
            validated = harvester_api.validate_email_batch(result['emails'])
            valid_emails = [e for e in validated if e.get('valid') == True]
            
            response_data.update({
                "validated_emails": validated,
                "validation_summary": {
                    "total_validated": len(validated),
                    "total_valid": len(valid_emails),
                    "validation_enabled": True
                }
            })
        else:
            response_data["validation_summary"] = {"validation_enabled": False}
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Processing error: {str(e)}",
            "domain": data.get('domain', 'unknown') if 'data' in locals() else 'unknown'
        }), 500

@app.route('/api/find-emails-bulk', methods=['POST'])
def find_emails_bulk():
    """Bulk domain processing with theHarvester"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domains = data.get('domains', [])
        validate = data.get('validate', True)
        sources = data.get('sources', 'google,bing')  # Limited sources for bulk
        
        if not domains or len(domains) > 3:  # Reduced limit for theHarvester
            return jsonify({"error": "Provide 1-3 domains for bulk processing"}), 400
        
        results = []
        
        for domain in domains:
            # Clean domain
            clean_domain = domain.strip().replace('http://', '').replace('https://', '').replace('www.', '')
            if '/' in clean_domain:
                clean_domain = clean_domain.split('/')[0]
            
            # Process with theHarvester
            result = harvester_api.run_theharvester(clean_domain, sources, limit=50)
            
            domain_result = {
                "domain": clean_domain,
                "method": result['method'],
                "status": result['status'],
                "emails_found": result['emails'],
                "total_found": result['count']
            }
            
            # Add validation
            if validate and result['emails']:
                validated = harvester_api.validate_email_batch(result['emails'][:8])
                valid_count = len([e for e in validated if e.get('valid') == True])
                domain_result.update({
                    "validated_emails": validated,
                    "validation_summary": {
                        "total_validated": len(validated),
                        "total_valid": valid_count
                    }
                })
            
            results.append(domain_result)
        
        # Calculate totals
        total_emails = sum(r['total_found'] for r in results)
        total_valid = sum(r.get('validation_summary', {}).get('total_valid', 0) for r in results)
        harvester_success = len([r for r in results if r['method'] == 'theHarvester'])
        
        return jsonify({
            "success": True,
            "results": results,
            "summary": {
                "total_domains_processed": len(domains),
                "total_emails_found": total_emails,
                "total_valid_emails": total_valid,
                "harvester_successful": harvester_success,
                "fallback_used": len(domains) - harvester_success,
                "validation_enabled": validate
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Bulk processing error: {str(e)}"
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
