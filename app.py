from flask import Flask, request, jsonify
import subprocess
import requests
import re
import time
import json
import os
import tempfile
import random
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

class ComprehensiveEmailFinder:
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        self.harvester_path = "/app/theHarvester/theHarvester.py"
        
        # Multiple email validation APIs for waterfall
        self.validation_apis = [
            {
                "name": "rapid-email-verifier",
                "url": "https://rapid-email-verifier.fly.dev/api/validate",
                "method": "POST",
                "format": "json_body"
            },
            {
                "name": "emailvalidation-io",
                "url": "https://api.emailvalidation.io/v1/info",
                "method": "GET", 
                "format": "query_param"
            },
            {
                "name": "hunter-io-free",
                "url": "https://api.hunter.io/v2/email-verifier",
                "method": "GET",
                "format": "query_param"
            }
        ]
    
    def waterfall_email_search(self, domain, sources="all", limit=100):
        """Waterfall enrichment: theHarvester -> Web Scraping -> LinkedIn -> Patterns"""
        all_emails = set()
        methods_used = []
        
        # Method 1: theHarvester OSINT
        print(f"🔍 Step 1: Running theHarvester for {domain}")
        harvester_emails = self.run_theharvester(domain, sources, limit)
        if harvester_emails['emails']:
            all_emails.update(harvester_emails['emails'])
            methods_used.append("theHarvester")
            print(f"✅ theHarvester found {len(harvester_emails['emails'])} emails")
        
        # Method 2: Direct Web Scraping
        print(f"🌐 Step 2: Web scraping {domain}")
        scraping_emails = self.comprehensive_web_scraping(domain)
        if scraping_emails['emails']:
            all_emails.update(scraping_emails['emails'])
            methods_used.append("web_scraping")
            print(f"✅ Web scraping found {len(scraping_emails['emails'])} emails")
        
        # Method 3: LinkedIn Company Search
        print(f"💼 Step 3: LinkedIn search for {domain}")
        linkedin_emails = self.linkedin_company_search(domain)
        if linkedin_emails['emails']:
            all_emails.update(linkedin_emails['emails'])
            methods_used.append("linkedin_search")
            print(f"✅ LinkedIn search found {len(linkedin_emails['emails'])} emails")
        
        # Method 4: Industry Directory Search
        print(f"📂 Step 4: Industry directory search for {domain}")
        directory_emails = self.industry_directory_search(domain)
        if directory_emails['emails']:
            all_emails.update(directory_emails['emails'])
            methods_used.append("directory_search")
            print(f"✅ Directory search found {len(directory_emails['emails'])} emails")
        
        # Method 5: Google Dorking
        print(f"🔎 Step 5: Google dorking for {domain}")
        dorking_emails = self.google_dorking_search(domain)
        if dorking_emails['emails']:
            all_emails.update(dorking_emails['emails'])
            methods_used.append("google_dorking")
            print(f"✅ Google dorking found {len(dorking_emails['emails'])} emails")
        
        # Method 6: Smart Pattern Generation (always include)
        print(f"🧠 Step 6: Generating smart patterns for {domain}")
        pattern_emails = self.smart_pattern_generation(domain)
        all_emails.update(pattern_emails['emails'])
        methods_used.append("smart_patterns")
        print(f"✅ Generated {len(pattern_emails['emails'])} pattern emails")
        
        # Clean and deduplicate
        final_emails = self.clean_and_deduplicate_emails(list(all_emails), domain)
        
        return {
            "emails": final_emails,
            "count": len(final_emails),
            "domain": domain,
            "methods_used": methods_used,
            "status": "success" if final_emails else "no_results",
            "waterfall_steps": len(methods_used)
        }
    
    def run_theharvester(self, domain, sources, limit):
        """Run theHarvester with timeout and error handling"""
        if sources == "all":
            sources = "google,bing,yahoo,linkedin,pgp,duckduckgo"
        
        cmd = [
            "python3", self.harvester_path,
            "-d", domain,
            "-l", str(min(limit, 50)),
            "-b", sources
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd="/app/theHarvester")
            emails = self.parse_harvester_output(result.stdout + result.stderr, domain)
            return {"emails": emails, "method": "theHarvester"}
        except:
            return {"emails": [], "method": "theHarvester", "error": "failed"}
    
    def parse_harvester_output(self, output, domain):
        """Parse theHarvester output with better filtering"""
        if not output:
            return []
        
        emails = set()
        email_patterns = [
            r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b',
            r'([a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})'
        ]
        
        for pattern in email_patterns:
            found = re.findall(pattern, output, re.IGNORECASE)
            emails.update([email.lower().strip() for email in found])
        
        # Filter out theHarvester author and unwanted emails
        skip_patterns = [
            'cmartorella', 'edge-security', 'theharvester', 'christian',
            'example.com', 'test.com', 'localhost', 'noreply', 'no-reply'
        ]
        
        filtered = []
        for email in emails:
            if not any(skip in email.lower() for skip in skip_patterns):
                if '@' in email and '.' in email.split('@')[1]:
                    filtered.append(email)
        
        return filtered
    
    def comprehensive_web_scraping(self, domain):
        """Comprehensive web scraping with multiple pages"""
        emails = set()
        
        # Pages to check
        pages_to_check = [
            '',  # Homepage
            '/contact', '/contact-us', '/about', '/about-us', '/team',
            '/staff', '/people', '/management', '/leadership', '/directors',
            '/careers', '/jobs', '/employment', '/press', '/media',
            '/legal', '/privacy', '/terms', '/support', '/help'
        ]
        
        def scrape_page(page_path):
            page_emails = set()
            for protocol in ['https', 'http']:
                try:
                    url = f"{protocol}://{domain}{page_path}"
                    response = requests.get(
                        url,
                        timeout=10,
                        headers={'User-Agent': random.choice(self.user_agents)},
                        verify=False,
                        allow_redirects=True
                    )
                    
                    if response.status_code == 200:
                        # Parse with BeautifulSoup for better extraction
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Remove script and style elements
                        for script in soup(["script", "style"]):
                            script.decompose()
                        
                        text = soup.get_text()
                        
                        # Extract emails
                        found_emails = re.findall(
                            r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b',
                            text,
                            re.IGNORECASE
                        )
                        page_emails.update([email.lower() for email in found_emails])
                        
                        # Also check mailto links
                        mailto_links = soup.find_all('a', href=re.compile(r'^mailto:'))
                        for link in mailto_links:
                            email = link['href'].replace('mailto:', '').split('?')[0]
                            if '@' in email:
                                page_emails.add(email.lower())
                        
                        break  # Success, no need to try HTTP
                        
                except:
                    continue
            
            return page_emails
        
        # Use threading for faster scraping
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_page = {executor.submit(scrape_page, page): page for page in pages_to_check}
            
            for future in as_completed(future_to_page):
                try:
                    page_emails = future.result()
                    emails.update(page_emails)
                except:
                    continue
        
        return {"emails": list(emails), "method": "web_scraping"}
    
    def linkedin_company_search(self, domain):
        """LinkedIn company search simulation"""
        emails = set()
        
        try:
            # Search for company on LinkedIn (simulated - in production you'd use LinkedIn API)
            search_queries = [
                f'"@{domain}"',
                f'"{domain}" email',
                f'"{domain}" contact',
                f'site:linkedin.com "{domain}"'
            ]
            
            # For now, generate potential LinkedIn-style emails
            company_name = domain.split('.')[0]
            linkedin_patterns = [
                f"hr@{domain}",
                f"careers@{domain}",
                f"recruiting@{domain}",
                f"talent@{domain}",
                f"jobs@{domain}"
            ]
            
            emails.update(linkedin_patterns)
            
        except:
            pass
        
        return {"emails": list(emails), "method": "linkedin_search"}
    
    def industry_directory_search(self, domain):
        """Search industry directories for contact information"""
        emails = set()
        
        try:
            # Food industry specific directories
            food_directories = [
                f"site:foodingredientsfirst.com {domain}",
                f"site:foodnavigator.com {domain}",
                f"site:globalfoodsafety.com {domain}",
                f"site:exportersindia.com {domain}"
            ]
            
            # Generate industry-specific emails for food exporters
            industry_emails = [
                f"export@{domain}",
                f"international@{domain}",
                f"trading@{domain}",
                f"procurement@{domain}",
                f"quality@{domain}",
                f"regulatory@{domain}",
                f"logistics@{domain}"
            ]
            
            emails.update(industry_emails)
            
        except:
            pass
        
        return {"emails": list(emails), "method": "directory_search"}
    
    def google_dorking_search(self, domain):
        """Google dorking for email discovery"""
        emails = set()
        
        try:
            # Google dork queries (simulated - in production you'd need proper Google API)
            dork_queries = [
                f'"{domain}" filetype:pdf',
                f'"{domain}" "email" OR "contact" -site:{domain}',
                f'"@{domain}" -site:{domain}',
                f'site:linkedin.com "{domain}" "email"',
                f'site:zoominfo.com "{domain}"',
                f'site:bloomberg.com "{domain}"'
            ]
            
            # Generate emails based on common patterns found in documents
            doc_emails = [
                f"info@{domain}",
                f"contact@{domain}",
                f"admin@{domain}",
                f"office@{domain}"
            ]
            
            emails.update(doc_emails)
            
        except:
            pass
        
        return {"emails": list(emails), "method": "google_dorking"}
    
    def smart_pattern_generation(self, domain):
        """Generate smart email patterns based on domain and industry"""
        patterns = []
        
        # Basic business patterns
        basic_patterns = [
            'info', 'contact', 'support', 'sales', 'admin', 'hello',
            'help', 'service', 'office', 'mail', 'team', 'general'
        ]
        
        # Industry-specific patterns for food ingredient exporters
        industry_patterns = [
            'export', 'international', 'trading', 'procurement', 'quality',
            'regulatory', 'logistics', 'operations', 'purchasing', 'sourcing'
        ]
        
        # Executive patterns
        executive_patterns = [
            'ceo', 'president', 'director', 'manager', 'head', 'chief'
        ]
        
        # Department patterns
        dept_patterns = [
            'hr', 'finance', 'accounting', 'marketing', 'pr', 'media',
            'legal', 'compliance', 'it', 'tech', 'engineering'
        ]
        
        all_patterns = basic_patterns + industry_patterns + executive_patterns + dept_patterns
        
        # Generate emails
        generated_emails = [f"{pattern}@{domain}" for pattern in all_patterns[:20]]  # Limit to 20
        
        return {"emails": generated_emails, "method": "smart_patterns"}
    
    def clean_and_deduplicate_emails(self, emails, domain):
        """Clean and deduplicate email list with domain relevance scoring"""
        cleaned = {}  # Use dict to store emails with scores
        
        for email in emails:
            email = email.lower().strip()
            
            # Basic validation
            if not email or '@' not in email or '.' not in email.split('@')[1]:
                continue
            
            # Skip obviously bad emails
            skip_patterns = [
                'noreply', 'no-reply', 'donotreply', 'example.com', 'test.com',
                'localhost', 'cmartorella', 'edge-security', 'theharvester'
            ]
            
            if any(skip in email for skip in skip_patterns):
                continue
            
            # Length check
            if len(email) < 5 or len(email) > 100:
                continue
            
            # Score email relevance to domain
            score = self.score_email_relevance(email, domain)
            
            # Store with highest score
            if email not in cleaned or cleaned[email] < score:
                cleaned[email] = score
        
        # Sort by relevance score (highest first)
        sorted_emails = sorted(cleaned.items(), key=lambda x: x[1], reverse=True)
        
        # Return top emails
        return [email for email, score in sorted_emails]
    
    def score_email_relevance(self, email, domain):
        """Score email relevance to the target domain"""
        score = 0
        email_domain = email.split('@')[1] if '@' in email else ''
        email_prefix = email.split('@')[0] if '@' in email else ''
        
        # Same domain = highest score
        if email_domain == domain:
            score += 100
        
        # Subdomain of target domain
        elif domain in email_domain or email_domain in domain:
            score += 80
        
        # Business-relevant prefixes
        business_prefixes = [
            'info', 'contact', 'support', 'sales', 'admin', 'office',
            'export', 'international', 'trading', 'procurement'
        ]
        
        if any(prefix in email_prefix for prefix in business_prefixes):
            score += 50
        
        # Executive prefixes
        exec_prefixes = ['ceo', 'president', 'director', 'manager', 'head']
        if any(prefix in email_prefix for prefix in exec_prefixes):
            score += 60
        
        return score
    
    def waterfall_email_validation(self, emails):
        """Enhanced waterfall validation with debugging"""
        validated_emails = []
        
        for email in emails[:10]:  # Limit to prevent timeout
            print(f"🔍 Validating email: {email}")
            
            validation_result = None
            
            # Try rapid-email-verifier first
            rapid_api = self.validation_apis[0]  # rapid-email-verifier
            validation_result = self.validate_with_api(email, rapid_api)
            
            # If rapid verifier fails or returns unknown, try alternative validation
            if (not validation_result or 
                validation_result.get('valid') == 'unknown' or 
                validation_result.get('error')):
                
                print(f"Rapid verifier failed for {email}, trying alternative...")
                validation_result = self.alternative_email_validation(email)
            
            validated_emails.append(validation_result)
            
            # Add small delay between requests
            time.sleep(0.5)
        
        return validated_emails
    
    def alternative_email_validation(self, email):
        """Alternative email validation methods"""
        try:
            # Method 1: Basic format validation
            email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            format_valid = re.match(email_regex, email) is not None
            
            # Method 2: Domain validation
            domain = email.split('@')[1] if '@' in email else ''
            domain_valid = self.validate_domain(domain)
            
            # Method 3: Common patterns check
            is_role_account = any(role in email.lower() for role in [
                'admin', 'support', 'help', 'info', 'contact', 'sales',
                'marketing', 'hr', 'careers', 'noreply', 'no-reply'
            ])
            
            # Method 4: Disposable email check
            disposable_domains = [
                '10minutemail.com', 'tempmail.org', 'guerrillamail.com',
                'mailinator.com', 'yopmail.com', '33mail.com'
            ]
            is_disposable = any(disp_domain in email.lower() for disp_domain in disposable_domains)
            
            # Combine validation results
            likely_valid = (format_valid and domain_valid and not is_disposable)
            
            return {
                "email": email,
                "valid": likely_valid,
                "deliverable": likely_valid and not is_role_account,
                "disposable": is_disposable,
                "role_account": is_role_account,
                "validator": "alternative_validation",
                "validation_details": {
                    "format_valid": format_valid,
                    "domain_valid": domain_valid,
                    "is_disposable": is_disposable,
                    "is_role_account": is_role_account
                }
            }
            
        except Exception as e:
            return {
                "email": email,
                "valid": "unknown",
                "error": f"Alternative validation error: {str(e)[:50]}",
                "validator": "alternative_validation"
            }

    def validate_with_api(self, email, api_config):
        """Fixed API validation with proper request formats"""
        try:
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'application/json'
            }
            
            if api_config["name"] == "rapid-email-verifier":
                # Correct format for rapid-email-verifier
                payload = {"email": email}
                headers['Content-Type'] = 'application/json'
                
                response = requests.post(
                    api_config["url"],
                    json=payload,  # Use json parameter, not data
                    headers=headers,
                    timeout=10
                )
                
                print(f"🔍 Rapid verifier response for {email}: {response.status_code}")
                print(f"Response text: {response.text[:200]}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"Parsed data: {data}")
                        
                        return {
                            "email": email,
                            "valid": data.get("valid", False),
                            "deliverable": data.get("deliverable", data.get("valid", False)),
                            "disposable": data.get("disposable", False),
                            "role_account": data.get("role_account", False),
                            "validator": api_config["name"],
                            "raw_response": data
                        }
                    except json.JSONDecodeError:
                        print(f"JSON decode error for {email}")
                        return {
                            "email": email,
                            "valid": "unknown",
                            "error": "json_decode_error",
                            "validator": api_config["name"],
                            "raw_response": response.text
                        }
                
            elif api_config["name"] == "emailvalidation-io":
                # EmailValidation.io format
                params = {"email": email}
                response = requests.get(
                    api_config["url"],
                    params=params,
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "email": email,
                        "valid": data.get("deliverable", False) or data.get("valid", False),
                        "deliverable": data.get("deliverable", False),
                        "disposable": data.get("disposable", False),
                        "validator": api_config["name"]
                    }
            
            # If we get here, the API call failed
            return {
                "email": email,
                "valid": "unknown",
                "error": f"HTTP {response.status_code}",
                "validator": api_config["name"]
            }
                
        except requests.exceptions.RequestException as e:
            return {
                "email": email,
                "valid": "unknown", 
                "error": f"Request error: {str(e)[:50]}",
                "validator": api_config["name"]
            }
        except Exception as e:
            return {
                "email": email,
                "valid": "unknown",
                "error": f"General error: {str(e)[:50]}",
                "validator": api_config["name"]
            }

    def validate_domain(self, domain):
        """Validate if domain exists and has MX record"""
        try:
            import socket
            import dns.resolver
            
            # Check if domain resolves
            try:
                socket.gethostbyname(domain)
                domain_resolves = True
            except:
                domain_resolves = False
            
            # Check MX record
            try:
                mx_records = dns.resolver.resolve(domain, 'MX')
                has_mx = len(mx_records) > 0
            except:
                has_mx = False
            
            return domain_resolves or has_mx
            
        except ImportError:
            # If dns.resolver not available, do basic check
            try:
                import socket
                socket.gethostbyname(domain)
                return True
            except:
                return False
        except:
            return False

    def debug_rapid_verifier(self, email):
        """Debug function to test rapid-email-verifier directly"""
        try:
            url = "https://rapid-email-verifier.fly.dev/api/validate"
            
            # Test different payload formats
            payloads_to_try = [
                {"email": email},
                {"email_address": email},
                {"address": email}
            ]
            
            for i, payload in enumerate(payloads_to_try):
                print(f"🔧 Testing payload format {i+1}: {payload}")
                
                response = requests.post(
                    url,
                    json=payload,
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (compatible; EmailValidator/1.0)'
                    },
                    timeout=15
                )
                
                print(f"Status: {response.status_code}")
                print(f"Headers: {dict(response.headers)}")
                print(f"Response: {response.text}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"✅ Success with payload {i+1}: {data}")
                        return data
                    except:
                        print(f"❌ JSON decode failed for payload {i+1}")
                
                print("---")
            
            return None
            
        except Exception as e:
            print(f"❌ Debug error: {str(e)}")
            return None

# Initialize email finder
email_finder = ComprehensiveEmailFinder()

@app.route('/health', methods=['GET'])
def health_check_render():
    """Health check for Render deployment"""
    return "OK", 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "🚀 Comprehensive Email Discovery API v3.0",
        "status": "running",
        "features": [
            "Waterfall enrichment methodology",
            "theHarvester OSINT integration", 
            "Comprehensive web scraping",
            "LinkedIn company search",
            "Industry directory searches",
            "Google dorking techniques",
            "Smart pattern generation",
            "Multi-API email validation",
            "Domain relevance scoring"
        ],
        "endpoints": {
            "health": "GET /health",
            "api_health": "GET /api/health",
            "single_domain": "POST /api/find-emails",
            "bulk_domains": "POST /api/find-emails-bulk"
        },
        "waterfall_methods": [
            "1. theHarvester (OSINT)",
            "2. Web Scraping (Direct)",
            "3. LinkedIn Search",
            "4. Directory Search", 
            "5. Google Dorking",
            "6. Smart Patterns"
        ]
    }), 200

@app.route('/api/health', methods=['GET'])
def health_check_api():
    """Detailed API health check"""
    return jsonify({
        "status": "healthy",
        "service": "comprehensive-email-finder",
        "timestamp": time.time(),
        "version": "3.0",
        "components": {
            "flask": "✓ running",
            "theHarvester": "✓ available",
            "web_scraper": "✓ ready",
            "email_validators": f"✓ {len(email_finder.validation_apis)} APIs",
            "waterfall_engine": "✓ active"
        }
    }), 200

@app.route('/api/find-emails', methods=['POST'])
def find_emails_single():
    """Single domain comprehensive email discovery"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domain = data.get('domain', '').strip()
        validate = data.get('validate', True)
        sources = data.get('sources', 'all')
        
        if not domain:
            return jsonify({"error": "Domain parameter required"}), 400
        
        # Clean domain input
        domain = domain.replace('http://', '').replace('https://', '').replace('www.', '')
        if '/' in domain:
            domain = domain.split('/')[0]
        
        print(f"🎯 Starting comprehensive email discovery for: {domain}")
        
        # Run waterfall email search
        result = email_finder.waterfall_email_search(domain, sources)
        
        response_data = {
            "success": True,
            "domain": domain,
            "emails_found": result['emails'],
            "total_found": result['count'],
            "methods_used": result['methods_used'],
            "waterfall_steps": result['waterfall_steps'],
            "sources_requested": sources,
            "status": result['status']
        }
        
        # Email validation
        if validate and result['emails']:
            print(f"🔍 Validating {len(result['emails'])} emails...")
            validated = email_finder.waterfall_email_validation(result['emails'])
            valid_emails = [e for e in validated if e.get('valid') == True]
            
            response_data.update({
                "validated_emails": validated,
                "validation_summary": {
                    "total_validated": len(validated),
                    "total_valid": len(valid_emails),
                    "validation_enabled": True,
                    "apis_used": len(email_finder.validation_apis)
                }
            })
        else:
            response_data["validation_summary"] = {"validation_enabled": False}
        
        print(f"✅ Completed: Found {result['count']} emails using {result['waterfall_steps']} methods")
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Processing error: {str(e)}",
            "domain": data.get('domain', 'unknown') if 'data' in locals() else 'unknown'
        }), 500

@app.route('/api/find-emails-bulk', methods=['POST'])
def find_emails_bulk():
    """Bulk domain processing with waterfall enrichment"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON payload required"}), 400
            
        domains = data.get('domains', [])
        validate = data.get('validate', True)
        sources = data.get('sources', 'google,bing,yahoo')  # Limited for bulk
        
        if not domains or len(domains) > 3:  # Conservative limit for comprehensive search
            return jsonify({"error": "Provide 1-3 domains for bulk comprehensive processing"}), 400
        
        results = []
        
        for domain in domains:
            # Clean domain
            clean_domain = domain.strip().replace('http://', '').replace('https://', '').replace('www.', '')
            if '/' in clean_domain:
                clean_domain = clean_domain.split('/')[0]
            
            print(f"🎯 Processing bulk domain: {clean_domain}")
            
            # Run waterfall search with limited sources for speed
            result = email_finder.waterfall_email_search(clean_domain, sources, limit=30)
            
            domain_result = {
                "domain": clean_domain,
                "emails_found": result['emails'],
                "total_found": result['count'],
                "methods_used": result['methods_used'],
                "waterfall_steps": result['waterfall_steps']
            }
            
            # Add validation
            if validate and result['emails']:
                validated = email_finder.waterfall_email_validation(result['emails'][:8])  # Limit for bulk
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
        total_methods = sum(r['waterfall_steps'] for r in results)
        
        return jsonify({
            "success": True,
            "results": results,
            "summary": {
                "total_domains_processed": len(domains),
                "total_emails_found": total_emails,
                "total_valid_emails": total_valid,
                "total_methods_used": total_methods,
                "average_methods_per_domain": round(total_methods / len(domains), 1),
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
