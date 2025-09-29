from flask import Flask, request, jsonify
import requests
import re
import time
import json
from urllib.parse import quote
import os

app = Flask(__name__)

class SimpleEmailFinder:
    def __init__(self):
        self.email_validator_url = "https://rapid-email-verifier.fly.dev/api/validate"
        
    def find_emails(self, domain, sources="patterns", limit=20):
        """Find emails using multiple methods"""
        all_emails = set()
        
        # Method 1: Common email patterns
        common_emails = self.generate_common_emails(domain)
        all_emails.update(common_emails)
        
        # Method 2: Web scraping (basic)
        try:
            scraped_emails = self.scrape_domain_emails(domain)
            all_emails.update(scraped_emails)
        except:
            pass
        
        # Filter and clean emails
        filtered_emails = self.filter_emails(list(all_emails), domain)
        
        return {
            "emails": filtered_emails[:limit],
            "count": len(filtered_emails[:limit]),
            "domain": domain,
            "method": "pattern_generation",
            "sources": sources
        }
    
    def generate_common_emails(self, domain):
        """Generate common email patterns for domain"""
        prefixes = [
            'info', 'contact', 'support', 'sales', 'admin', 'hello',
            'help', 'service', 'office', 'mail', 'team', 'general',
            'inquiry', 'customer', 'business', 'marketing', 'hr',
            'careers', 'pr', 'media', 'press', 'legal', 'finance'
        ]
        
        return [f"{prefix}@{domain}" for prefix in prefixes]
    
    def scrape_domain_emails(self, domain):
        """Basic domain scraping for emails"""
        emails = set()
        
        try:
            # Try to get the domain's main page
            response = requests.get(
                f"https://{domain}",
                timeout=5,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                verify=False
            )
            
            if response.status_code == 200:
                # Extract emails from page content
                email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                found_emails = re.findall(email_pattern, response.text)
                emails.update(found_emails)
                
        except:
            pass
        
        return list(emails)
    
    def filter_emails(self, emails, domain):
        """Filter and validate email format"""
        filtered = []
        skip_patterns = [
            'noreply', 'no-reply', 'donotreply', 'example.com',
            'test.com', 'localhost', 'sentry'
        ]
        
        for email in emails:
            email = email.lower().strip()
            if '@' in email and '.' in email.split('@')[1]:
                if not any(skip in email for skip in skip_patterns):
                    filtered.append(email)
        
        return list(set(filtered))
    
    def validate_email_batch(self, emails):
        """Validate emails using free validator API"""
        validated_emails = []
        
        for email in emails[:10]:  # Limit to prevent abuse
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

# Initialize email finder
email_finder = SimpleEmailFinder()

# RENDER HEALTH CHECK - CRITICAL
@app.route('/health', methods=['GET'])
def health_check_render():
    """Health check endpoint for Render deployment"""
    return "OK", 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "🔍 Email Finder API v1.0",
        "status": "running",
        "method": "pattern_generation_and_scraping",
        "endpoints": {
            "health": "GET /health",
            "api_health": "GET /api/health", 
            "single_domain": "POST /api/find-emails",
            "bulk_domains": "POST /api/find-emails-bulk"
        },
        "example": {
            "domain": "example.com",
            "validate": True
        }
    }), 200

@app.route('/api/health', methods=['GET'])
def health_check_api():
    """API health check with details"""
    return jsonify({
        "status": "healthy",
        "service": "email-finder-api",
        "timestamp": time.time(),
        "version": "1.0",
        "components": {
            "flask": "✓ running",
            "email_validator": "✓ available",
            "pattern_generator": "✓ ready"
        }
    }), 200

@app.route('/api/find-emails', methods=['POST'])
def find_emails_single():
    """Single domain email finding"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domain = data.get('domain', '').strip()
        validate = data.get('validate', True)
        sources = data.get('sources', 'patterns')
        
        if not domain:
            return jsonify({"error": "Domain parameter required"}), 400
        
        # Clean domain
        domain = domain.replace('http://', '').replace('https://', '').replace('www.', '')
        if '/' in domain:
            domain = domain.split('/')[0]
        
        # Find emails
        result = email_finder.find_emails(domain, sources)
        
        response_data = {
            "success": True,
            "domain": domain,
            "emails_found": result['emails'],
            "total_found": result['count'],
            "method": result['method'],
            "sources_used": sources
        }
        
        # Add validation if requested
        if validate and result['emails']:
            validated = email_finder.validate_email_batch(result['emails'])
            valid_emails = [e for e in validated if e.get('valid') == True]
            
            response_data.update({
                "validated_emails": validated,
                "validation_summary": {
                    "total_validated": len(validated),
                    "total_valid": len(valid_emails)
                }
            })
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Processing error: {str(e)}",
            "domain": data.get('domain', 'unknown') if 'data' in locals() else 'unknown'
        }), 500

@app.route('/api/find-emails-bulk', methods=['POST'])
def find_emails_bulk():
    """Bulk domain processing"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domains = data.get('domains', [])
        validate = data.get('validate', True)
        
        if not domains or len(domains) > 5:
            return jsonify({"error": "Provide 1-5 domains"}), 400
        
        results = []
        
        for domain in domains:
            # Clean domain
            clean_domain = domain.strip().replace('http://', '').replace('https://', '').replace('www.', '')
            if '/' in clean_domain:
                clean_domain = clean_domain.split('/')[0]
            
            # Find emails
            result = email_finder.find_emails(clean_domain, "patterns")
            
            domain_result = {
                "domain": clean_domain,
                "emails_found": result['emails'],
                "total_found": result['count']
            }
            
            # Add validation
            if validate and result['emails']:
                validated = email_finder.validate_email_batch(result['emails'][:5])
                valid_count = len([e for e in validated if e.get('valid') == True])
                domain_result.update({
                    "validated_emails": validated,
                    "validation_summary": {
                        "total_validated": len(validated),
                        "total_valid": valid_count
                    }
                })
            
            results.append(domain_result)
        
        # Calculate summary
        total_emails = sum(r['total_found'] for r in results)
        total_valid = sum(r.get('validation_summary', {}).get('total_valid', 0) for r in results)
        
        return jsonify({
            "success": True,
            "results": results,
            "summary": {
                "total_domains": len(domains),
                "total_emails_found": total_emails,
                "total_valid_emails": total_valid
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
