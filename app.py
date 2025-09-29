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
        """Run theHarvester with proper error handling"""
        
        # Create temporary file for output
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp_file:
            temp_filename = tmp_file.name
        
        # Command to run theHarvester
        cmd = [
            "python3", self.harvester_path,
            "-d", domain,
            "-l", str(limit), 
            "-b", sources,
            "-f", temp_filename.replace('.json', '')  # theHarvester adds extension
        ]
        
        try:
            # Run theHarvester with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd="/app/theHarvester"
            )
            
            # Extract emails from stdout and file
            emails = self.extract_emails_from_harvester(result.stdout, temp_filename)
            
            # Clean up temp file
            try:
                os.unlink(temp_filename)
                os.unlink(temp_filename.replace('.json', '.xml'))
                os.unlink(temp_filename.replace('.json', '.html'))
            except:
                pass
            
            return {
                "emails": emails,
                "count": len(emails),
                "domain": domain,
                "sources": sources,
                "method": "theHarvester",
                "status": "success",
                "raw_output": result.stdout[:500] if result.stdout else "No output"
            }
            
        except subprocess.TimeoutExpired:
            return self.fallback_with_patterns(domain, "timeout")
        except subprocess.CalledProcessError as e:
            return self.fallback_with_patterns(domain, f"process_error: {e}")
        except Exception as e:
            return self.fallback_with_patterns(domain, f"general_error: {str(e)}")
    
    def extract_emails_from_harvester(self, stdout, temp_filename):
        """Extract emails from theHarvester output"""
        emails = set()
        
        # Method 1: Extract from stdout
        if stdout:
            email_patterns = [
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                r'[\w\.-]+@[\w\.-]+\.\w+',
                r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            ]
            
            for pattern in email_patterns:
                found_emails = re.findall(pattern, stdout, re.IGNORECASE)
                emails.update(found_emails)
        
        # Method 2: Try to read from output files
        possible_files = [
            temp_filename,
            temp_filename.replace('.json', '.xml'),
            temp_filename.replace('.json', '.html'),
            temp_filename.replace('.json', '.txt')
        ]
        
        for file_path in possible_files:
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        file_emails = re.findall(
                            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 
                            content, 
                            re.IGNORECASE
                        )
                        emails.update(file_emails)
            except:
                continue
        
        # Filter emails
        return self.filter_emails(list(emails))
    
    def filter_emails(self, emails):
        """Filter out invalid and unwanted emails"""
        filtered = []
        skip_patterns = [
            'noreply', 'no-reply', 'donotreply', 'example.com', 'test.com',
            'localhost', 'sentry', 'github.com', 'gitlab.com', 'stackoverflow.com',
            'linkedin.com', 'facebook.com', 'twitter.com', 'instagram.com'
        ]
        
        for email in emails:
            email = email.lower().strip()
            if '@' in email and '.' in email.split('@')[1]:
                if not any(skip in email for skip in skip_patterns):
                    if len(email) > 5 and len(email) < 100:  # Reasonable length
                        filtered.append(email)
        
        return list(set(filtered))
    
    def fallback_with_patterns(self, domain, error_reason):
        """Fallback to pattern generation when theHarvester fails"""
        prefixes = [
            'info', 'contact', 'support', 'sales', 'admin', 'hello',
            'help', 'service', 'office', 'mail', 'team', 'general'
        ]
        
        fallback_emails = [f"{prefix}@{domain}" for prefix in prefixes]
        
        return {
            "emails": fallback_emails,
            "count": len(fallback_emails),
            "domain": domain,
            "method": "fallback_patterns",
            "status": "fallback",
            "error": error_reason,
            "note": "theHarvester failed, using pattern generation"
        }
    
    def validate_email_batch(self, emails):
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
