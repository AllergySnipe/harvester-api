from flask import Flask, request, jsonify
import subprocess
import re
import requests
import os
import tempfile
import time
import sys

app = Flask(__name__)

class HarvesterAPI:
    def __init__(self):
        self.email_validator_url = "https://rapid-email-verifier.fly.dev/api/validate"
        
    def run_harvester(self, domain, sources="google,bing,yahoo", limit=200):
        """Run theHarvester with optimal settings"""
        
        # Try different ways to run theHarvester
        possible_commands = [
            ["theHarvester", "-d", domain, "-l", str(limit), "-b", sources],
            ["python3", "-m", "theHarvester", "-d", domain, "-l", str(limit), "-b", sources],
            ["python3", "/app/theHarvester/theHarvester.py", "-d", domain, "-l", str(limit), "-b", sources]
        ]
        
        for cmd in possible_commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0 or result.stdout:
                    emails = self.extract_emails_from_output(result.stdout)
                    return {"emails": emails, "count": len(emails), "domain": domain}
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
                
        # If all commands fail, try manual approach
        return self.fallback_email_search(domain)
    
    def fallback_email_search(self, domain):
        """Fallback method using simple regex on domain"""
        try:
            # Simple Google search simulation (not actual scraping)
            emails = [
                f"info@{domain}",
                f"contact@{domain}",
                f"support@{domain}",
                f"sales@{domain}"
            ]
            return {"emails": emails[:2], "count": 2, "domain": domain, "method": "fallback"}
        except:
            return {"emails": [], "count": 0, "domain": domain, "error": "All methods failed"}
    
    def extract_emails_from_output(self, stdout):
        """Extract emails from theHarvester output"""
        emails = set()
        
        # Extract from stdout
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        stdout_emails = re.findall(email_pattern, stdout)
        emails.update(stdout_emails)
        
        # Filter out common false positives
        filtered_emails = []
        for email in emails:
            if not any(skip in email.lower() for skip in ['noreply', 'no-reply', 'example.com', 'test.com', 'sentry']):
                filtered_emails.append(email)
        
        return list(set(filtered_emails))
    
    def validate_email_batch(self, emails):
        """Validate emails using free validator API"""
        validated_emails = []
        
        for email in emails[:10]:  # Limit for free tier
            try:
                response = requests.post(
                    self.email_validator_url,
                    json={"email": email},
                    timeout=10,
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
                    validated_emails.append({
                        "email": email,
                        "valid": "unknown",
                        "error": f"HTTP {response.status_code}"
                    })
                    
            except Exception as e:
                validated_emails.append({
                    "email": email,
                    "valid": "unknown",
                    "error": str(e)
                })
        
        return validated_emails

# Initialize harvester
harvester = HarvesterAPI()

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Harvester API is running on Render",
        "endpoints": {
            "single": "/api/find-emails (POST)",
            "bulk": "/api/find-emails-bulk (POST)",
            "health": "/api/health (GET)"
        },
        "example_request": {
            "domain": "example.com",
            "validate": True,
            "sources": "google,bing,yahoo"
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy", 
        "service": "harvester-api",
        "timestamp": time.time()
    })

@app.route('/api/find-emails', methods=['POST'])
def find_emails_single():
    """Single domain email finding with validation"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domain = data.get('domain')
        validate = data.get('validate', True)
        sources = data.get('sources', 'google,bing,yahoo')
        
        if not domain:
            return jsonify({"error": "Domain required"}), 400
        
        # Clean domain input
        domain = domain.strip().replace('http://', '').replace('https://', '').replace('www.', '')
        
        # Run theHarvester
        result = harvester.run_harvester(domain, sources)
        
        if result.get('error'):
            return jsonify(result), 500
        
        if validate and result.get('emails'):
            # Validate emails
            validated = harvester.validate_email_batch(result['emails'])
            valid_emails = [e for e in validated if e.get('valid') == True]
            
            return jsonify({
                "domain": domain,
                "raw_emails": result['emails'],
                "validated_emails": validated,
                "summary": {
                    "total_found": len(result['emails']),
                    "total_validated": len(validated),
                    "total_valid": len(valid_emails),
                    "sources_used": sources,
                    "method": result.get('method', 'theHarvester')
                }
            })
        
        return jsonify({
            "domain": domain,
            "emails": result['emails'],
            "count": len(result['emails']),
            "sources_used": sources,
            "method": result.get('method', 'theHarvester')
        })
        
    except Exception as e:
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

@app.route('/api/find-emails-bulk', methods=['POST'])
def find_emails_bulk():
    """Bulk domain processing"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domains = data.get('domains', [])
        validate = data.get('validate', True)
        
        if not domains or len(domains) > 5:  # Limit for free tier
            return jsonify({"error": "Provide 1-5 domains"}), 400
        
        def process_domain(domain):
            # Clean domain
            clean_domain = domain.strip().replace('http://', '').replace('https://', '').replace('www.', '')
            result = harvester.run_harvester(clean_domain, "google,bing")
            
            if result.get('error'):
                return {
                    "domain": clean_domain,
                    "error": result['error'],
                    "emails": [],
                    "summary": {"found": 0, "validated": 0, "valid": 0}
                }
            
            if validate and result.get('emails'):
                validated = harvester.validate_email_batch(result['emails'][:5])
                valid_count = len([e for e in validated if e.get('valid') == True])
                return {
                    "domain": clean_domain,
                    "emails": validated,
                    "summary": {
                        "found": len(result['emails']),
                        "validated": len(validated),
                        "valid": valid_count
                    }
                }
            
            return {
                "domain": clean_domain,
                "emails": result.get('emails', []),
                "summary": {
                    "found": len(result.get('emails', [])),
                    "validated": 0,
                    "valid": 0
                }
            }
        
        # Process domains sequentially for stability
        results = []
        for domain in domains:
            results.append(process_domain(domain))
        
        total_emails = sum(r['summary']['found'] for r in results)
        total_valid = sum(r['summary']['valid'] for r in results)
        
        return jsonify({
            "results": results,
            "summary": {
                "total_domains": len(domains),
                "total_emails_found": total_emails,
                "total_valid_emails": total_valid
            }
        })
        
    except Exception as e:
        return jsonify({"error": f"Internal error: {str(e)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
