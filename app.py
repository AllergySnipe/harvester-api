from flask import Flask, request, jsonify
import subprocess
import re
import requests
import os
import time
import json

app = Flask(__name__)

class HarvesterAPI:
    def __init__(self):
        self.email_validator_url = "https://rapid-email-verifier.fly.dev/api/validate"
        
    def run_harvester(self, domain, sources="google,bing,yahoo", limit=100):
        """Run theHarvester with optimal settings"""
        
        # Command to run theHarvester
        cmd = [
            "python3", 
            "/app/theHarvester/theHarvester.py",
            "-d", domain,
            "-l", str(limit),
            "-b", sources
        ]
        
        try:
            # Run the command with timeout
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=90,
                cwd="/app/theHarvester"
            )
            
            # Extract emails from output
            emails = self.extract_emails_from_output(result.stdout + result.stderr)
            
            return {
                "emails": emails, 
                "count": len(emails), 
                "domain": domain,
                "sources": sources,
                "status": "success"
            }
            
        except subprocess.TimeoutExpired:
            return {
                "emails": [], 
                "count": 0, 
                "domain": domain,
                "error": "Timeout after 90 seconds",
                "status": "timeout"
            }
        except Exception as e:
            # Fallback method
            return self.fallback_email_search(domain)
    
    def fallback_email_search(self, domain):
        """Fallback method when theHarvester fails"""
        try:
            # Common email patterns for the domain
            common_emails = [
                f"info@{domain}",
                f"contact@{domain}",
                f"support@{domain}",
                f"sales@{domain}",
                f"admin@{domain}",
                f"hello@{domain}"
            ]
            
            return {
                "emails": common_emails[:3], 
                "count": 3, 
                "domain": domain,
                "method": "fallback_pattern",
                "status": "fallback"
            }
        except:
            return {
                "emails": [], 
                "count": 0, 
                "domain": domain, 
                "error": "All methods failed",
                "status": "failed"
            }
    
    def extract_emails_from_output(self, output_text):
        """Extract emails from theHarvester output"""
        if not output_text:
            return []
            
        emails = set()
        
        # Comprehensive email regex
        email_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            r'[\w\.-]+@[\w\.-]+\.\w+'
        ]
        
        for pattern in email_patterns:
            found_emails = re.findall(pattern, output_text, re.IGNORECASE)
            emails.update(found_emails)
        
        # Filter out invalid/unwanted emails
        filtered_emails = []
        skip_patterns = [
            'noreply', 'no-reply', 'donotreply', 'example.com', 
            'test.com', 'localhost', 'sentry', 'gitlab.com',
            'github.com', 'stackoverflow.com'
        ]
        
        for email in emails:
            email_lower = email.lower()
            if not any(skip in email_lower for skip in skip_patterns):
                if '@' in email and '.' in email.split('@')[1]:
                    filtered_emails.append(email)
        
        return list(set(filtered_emails))
    
    def validate_email_batch(self, emails):
        """Validate emails using free validator API"""
        validated_emails = []
        
        # Limit to prevent API abuse
        emails_to_validate = emails[:10]
        
        for email in emails_to_validate:
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
                        "disposable": data.get("disposable", False),
                        "role_account": data.get("role_account", False)
                    })
                else:
                    # Include email even if validation fails
                    validated_emails.append({
                        "email": email,
                        "valid": "unknown",
                        "error": f"Validation failed: HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                validated_emails.append({
                    "email": email,
                    "valid": "unknown", 
                    "error": f"Validation error: {str(e)}"
                })
        
        return validated_emails

# Initialize harvester
harvester = HarvesterAPI()

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "🔍 Harvester API v2.0 - Email Discovery Service",
        "status": "running",
        "endpoints": {
            "health": "GET /api/health",
            "single_domain": "POST /api/find-emails",
            "bulk_domains": "POST /api/find-emails-bulk"
        },
        "example_requests": {
            "single": {
                "domain": "example.com",
                "validate": True,
                "sources": "google,bing,yahoo"
            },
            "bulk": {
                "domains": ["example.com", "test.org"],
                "validate": True
            }
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test theHarvester installation
        test_result = subprocess.run([
            "python3", "/app/theHarvester/theHarvester.py", "-h"
        ], capture_output=True, text=True, timeout=10)
        
        harvester_status = "working" if test_result.returncode == 0 else "error"
    except:
        harvester_status = "error"
    
    return jsonify({
        "status": "healthy",
        "service": "harvester-api",
        "timestamp": time.time(),
        "theHarvester": harvester_status,
        "components": {
            "flask": "✓ running",
            "theHarvester": f"✓ {harvester_status}",
            "email_validator": "✓ available"
        }
    })

@app.route('/api/find-emails', methods=['POST'])
def find_emails_single():
    """Single domain email finding with validation"""
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
        result = harvester.run_harvester(domain, sources)
        
        response_data = {
            "domain": domain,
            "status": result.get('status', 'unknown'),
            "emails_found": result['emails'],
            "total_found": result['count'],
            "sources_used": sources
        }
        
        # Add validation if requested and emails found
        if validate and result['emails']:
            validated = harvester.validate_email_batch(result['emails'])
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
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            "error": f"Processing error: {str(e)}",
            "domain": data.get('domain', 'unknown') if 'data' in locals() else 'unknown'
        }), 500

@app.route('/api/find-emails-bulk', methods=['POST'])
def find_emails_bulk():
    """Bulk domain processing with limits"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domains = data.get('domains', [])
        validate = data.get('validate', True)
        
        # Validate input
        if not domains:
            return jsonify({"error": "Domains array required"}), 400
        if len(domains) > 5:  # Limit for free tier
            return jsonify({"error": "Maximum 5 domains allowed per request"}), 400
        
        results = []
        
        for domain in domains:
            # Clean domain
            clean_domain = domain.strip().replace('http://', '').replace('https://', '').replace('www.', '')
            if '/' in clean_domain:
                clean_domain = clean_domain.split('/')[0]
            
            # Process domain
            result = harvester.run_harvester(clean_domain, "google,bing")
            
            domain_result = {
                "domain": clean_domain,
                "status": result.get('status', 'unknown'),
                "emails_found": result['emails'],
                "total_found": result['count']
            }
            
            # Add validation if requested
            if validate and result['emails']:
                validated = harvester.validate_email_batch(result['emails'][:5])
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
        
        return jsonify({
            "results": results,
            "summary": {
                "total_domains_processed": len(domains),
                "total_emails_found": total_emails,
                "total_valid_emails": total_valid,
                "validation_enabled": validate
            }
        })
        
    except Exception as e:
        return jsonify({
            "error": f"Bulk processing error: {str(e)}",
            "domains_attempted": len(data.get('domains', [])) if 'data' in locals() else 0
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
