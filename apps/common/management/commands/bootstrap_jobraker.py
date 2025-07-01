"""
Bootstrap Jobraker system with initial data and configurations.
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Bootstrap Jobraker system with initial data and configurations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--create-admin',
            action='store_true',
            help='Create a superuser account',
        )
        parser.add_argument(
            '--setup-email-templates',
            action='store_true',
            help='Create default email templates',
        )
        parser.add_argument(
            '--setup-knowledge-base',
            action='store_true',
            help='Create sample knowledge articles',
        )
        parser.add_argument(
            '--test-integrations',
            action='store_true',
            help='Test external API integrations',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Run all bootstrap tasks',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting Jobraker Bootstrap Process...')
        )

        if options['all']:
            options['create_admin'] = True
            options['setup_email_templates'] = True
            options['setup_knowledge_base'] = True
            options['test_integrations'] = True

        if options['create_admin']:
            self.create_admin_user()

        if options['setup_email_templates']:
            self.setup_email_templates()

        if options['setup_knowledge_base']:
            self.setup_knowledge_base()

        if options['test_integrations']:
            self.test_integrations()

        self.stdout.write(
            self.style.SUCCESS('✅ Jobraker Bootstrap Complete!')
        )

    def create_admin_user(self):
        """Create a superuser account if it doesn't exist."""
        self.stdout.write('Creating admin user...')
        
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING('Superuser already exists. Skipping...')
            )
            return

        try:
            admin_user = User.objects.create_superuser(
                email='admin@jobraker.com',
                password='admin123',
                first_name='Admin',
                last_name='User'
            )
            
            # Create profile for admin user
            from apps.accounts.models import UserProfile
            profile, created = UserProfile.objects.get_or_create(
                user=admin_user,
                defaults={
                    'current_title': 'System Administrator',
                    'experience_level': 'senior',
                    'skills': ['System Administration', 'Django', 'Python'],
                    'bio': 'System administrator for Jobraker platform',
                    'location': 'System',
                    'email_notifications': True
                }
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Created admin user: admin@jobraker.com / admin123'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error creating admin user: {e}')
            )

    def setup_email_templates(self):
        """Create default email templates."""
        self.stdout.write('Setting up email templates...')
        
        from apps.common.models import EmailTemplate
        
        templates = [
            {
                'name': 'welcome',
                'description': 'Welcome email for new users',
                'subject_template': 'Welcome to {{ site_name }}!',
                'html_template': '''
                <h1>Welcome to {{ site_name }}, {{ recipient_name }}!</h1>
                <p>Thank you for joining our AI-powered job search platform.</p>
                <p>Get started by:</p>
                <ul>
                    <li><a href="{{ dashboard_url }}">Setting up your profile</a></li>
                    <li><a href="{{ getting_started_url }}">Exploring job recommendations</a></li>
                </ul>
                <p>Best regards,<br>The {{ site_name }} Team</p>
                ''',
                'text_template': '''
                Welcome to {{ site_name }}, {{ recipient_name }}!
                
                Thank you for joining our AI-powered job search platform.
                
                Get started by visiting: {{ dashboard_url }}
                
                Best regards,
                The {{ site_name }} Team
                ''',
                'category': 'welcome',
                'variables': ['recipient_name', 'site_name', 'dashboard_url', 'getting_started_url']
            },
            {
                'name': 'job_alert',
                'description': 'Job alert notification email',
                'subject_template': 'New Job Matches: {{ jobs_count }} opportunities for {{ alert_name }}',
                'html_template': '''
                <h1>New Job Opportunities!</h1>
                <p>Hi {{ recipient_name }},</p>
                <p>We found {{ jobs_count }} new job(s) matching your alert "{{ alert_name }}":</p>
                
                {% for job in jobs %}
                <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0;">
                    <h3>{{ job.title }} at {{ job.company }}</h3>
                    <p><strong>Location:</strong> {{ job.location }}</p>
                    <p><strong>Salary:</strong> {{ job.salary_range }}</p>
                    <p><strong>Type:</strong> {{ job.job_type }}</p>
                    <a href="{{ job.url }}" style="background: #007cba; color: white; padding: 10px 15px; text-decoration: none;">View Job</a>
                    <a href="{{ job.apply_url }}" style="background: #28a745; color: white; padding: 10px 15px; text-decoration: none; margin-left: 10px;">Quick Apply</a>
                </div>
                {% endfor %}
                
                <p>Happy job hunting!<br>The {{ site_name }} Team</p>
                ''',
                'text_template': '''
                New Job Opportunities!
                
                Hi {{ recipient_name }},
                
                We found {{ jobs_count }} new job(s) matching your alert "{{ alert_name }}":
                
                {% for job in jobs %}
                {{ job.title }} at {{ job.company }}
                Location: {{ job.location }}
                Salary: {{ job.salary_range }}
                View: {{ job.url }}
                Apply: {{ job.apply_url }}
                
                {% endfor %}
                
                Happy job hunting!
                The {{ site_name }} Team
                ''',
                'category': 'job_alert',
                'variables': ['recipient_name', 'site_name', 'alert_name', 'jobs_count', 'jobs']
            },
            {
                'name': 'application_status',
                'description': 'Application status update email',
                'subject_template': 'Application Update: {{ job_title }} at {{ company_name }}',
                'html_template': '''
                <h1>Application Status Update</h1>
                <p>Hi {{ recipient_name }},</p>
                <p>Your application for <strong>{{ job_title }}</strong> at <strong>{{ company_name }}</strong> has been updated:</p>
                
                <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #007cba; margin: 20px 0;">
                    <p><strong>Status:</strong> {{ status }}</p>
                    {% if additional_info %}
                    <p><strong>Additional Information:</strong> {{ additional_info }}</p>
                    {% endif %}
                </div>
                
                <p>Best regards,<br>The {{ site_name }} Team</p>
                ''',
                'text_template': '''
                Application Status Update
                
                Hi {{ recipient_name }},
                
                Your application for {{ job_title }} at {{ company_name }} has been updated:
                
                Status: {{ status }}
                {% if additional_info %}
                Additional Information: {{ additional_info }}
                {% endif %}
                
                Best regards,
                The {{ site_name }} Team
                ''',
                'category': 'application_status',
                'variables': ['recipient_name', 'site_name', 'job_title', 'company_name', 'status', 'additional_info']
            }
        ]
        
        created_count = 0
        for template_data in templates:
            template, created = EmailTemplate.objects.get_or_create(
                name=template_data['name'],
                defaults=template_data
            )
            if created:
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Created {created_count} email templates')
        )

    def setup_knowledge_base(self):
        """Create sample knowledge articles."""
        self.stdout.write('Setting up knowledge base...')
        
        from apps.common.models import KnowledgeArticle
        
        articles = [
            {
                'title': 'How to Write an Effective Resume',
                'content': '''
                Writing an effective resume is crucial for landing job interviews. Here are key tips:

                1. **Keep it concise**: Limit to 1-2 pages for most positions
                2. **Use action verbs**: Start bullet points with strong action verbs
                3. **Quantify achievements**: Include numbers and metrics where possible
                4. **Tailor for each job**: Customize your resume for each application
                5. **Include keywords**: Use keywords from the job description
                6. **Proper formatting**: Use clean, professional formatting
                7. **Contact information**: Ensure your contact details are current
                8. **Professional email**: Use a professional email address

                Remember to proofread carefully and have someone else review your resume before submitting.
                ''',
                'category': 'resume',
                'tags': ['resume', 'cv', 'writing', 'job search'],
                'slug': 'how-to-write-effective-resume',
                'excerpt': 'Learn the essential tips for creating a resume that gets you noticed by employers.',
                'is_published': True,
                'author_name': 'Jobraker Team'
            },
            {
                'title': 'Interview Preparation Guide',
                'content': '''
                Preparing for job interviews is essential for success. Follow this comprehensive guide:

                **Before the Interview:**
                - Research the company thoroughly
                - Review the job description carefully
                - Prepare answers using the STAR method
                - Plan your outfit and route
                - Prepare thoughtful questions to ask

                **Common Interview Questions:**
                - Tell me about yourself
                - Why do you want this job?
                - What are your strengths and weaknesses?
                - Where do you see yourself in 5 years?
                - Why are you leaving your current job?

                **During the Interview:**
                - Arrive 10-15 minutes early
                - Maintain good body language
                - Listen actively and ask clarifying questions
                - Provide specific examples
                - Show enthusiasm for the role

                **After the Interview:**
                - Send a thank-you email within 24 hours
                - Follow up appropriately
                - Reflect on the experience
                ''',
                'category': 'interview',
                'tags': ['interview', 'preparation', 'questions', 'tips'],
                'slug': 'interview-preparation-guide',
                'excerpt': 'Complete guide to preparing for and succeeding in job interviews.',
                'is_published': True,
                'author_name': 'Jobraker Team'
            },
            {
                'title': 'Salary Negotiation Strategies',
                'content': '''
                Negotiating your salary can be intimidating, but it's a crucial skill. Here's how to do it effectively:

                **Research and Preparation:**
                - Research market rates for your position
                - Use salary comparison websites
                - Consider your total compensation package
                - Know your minimum acceptable offer

                **When to Negotiate:**
                - After receiving a job offer
                - During performance reviews
                - When taking on additional responsibilities
                - When you have competing offers

                **Negotiation Tactics:**
                - Start with a higher number than your target
                - Focus on your value and contributions
                - Be professional and respectful
                - Consider non-salary benefits
                - Get everything in writing

                **What to Negotiate:**
                - Base salary
                - Bonus structure
                - Vacation time
                - Flexible work arrangements
                - Professional development opportunities
                - Stock options or equity

                Remember, negotiation is a normal part of the hiring process, and employers often expect it.
                ''',
                'category': 'salary',
                'tags': ['salary', 'negotiation', 'compensation', 'benefits'],
                'slug': 'salary-negotiation-strategies',
                'excerpt': 'Learn effective strategies for negotiating your salary and benefits package.',
                'is_published': True,
                'author_name': 'Jobraker Team'
            }
        ]
        
        created_count = 0
        for article_data in articles:
            article, created = KnowledgeArticle.objects.get_or_create(
                slug=article_data['slug'],
                defaults=article_data
            )
            if created:
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ Created {created_count} knowledge articles')
        )

    def test_integrations(self):
        """Test external API integrations."""
        self.stdout.write('Testing external integrations...')
        
        # Test OpenAI
        openai_status = self._test_openai()
        
        # Test Adzuna
        adzuna_status = self._test_adzuna()
        
        # Test Redis/Celery
        redis_status = self._test_redis()
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write('INTEGRATION TEST RESULTS:')
        self.stdout.write('='*50)
        self.stdout.write(f'OpenAI API: {openai_status}')
        self.stdout.write(f'Adzuna API: {adzuna_status}')
        self.stdout.write(f'Redis/Celery: {redis_status}')
        self.stdout.write('='*50)

    def _test_openai(self):
        """Test OpenAI API connection."""
        try:
            from apps.integrations.services.openai import OpenAIClient
            
            client = OpenAIClient()
            if not client.api_key:
                return self.style.WARNING('⚠️ NOT CONFIGURED')
            
            # Test simple embedding
            test_embedding = client.generate_embedding("test text")
            if test_embedding and len(test_embedding) > 0:
                return self.style.SUCCESS('✅ WORKING')
            else:
                return self.style.ERROR('❌ FAILED')
                
        except Exception as e:
            return self.style.ERROR(f'❌ ERROR: {e}')

    def _test_adzuna(self):
        """Test Adzuna API connection."""
        try:
            from apps.integrations.services.adzuna import AdzunaAPIClient
            
            client = AdzunaAPIClient()
            if not client.app_id or not client.api_key:
                return self.style.WARNING('⚠️ NOT CONFIGURED')
            
            # Test simple job search
            response = client.search_jobs(what="python", where="us", results_per_page=1)
            if response and 'results' in response:
                return self.style.SUCCESS('✅ WORKING')
            else:
                return self.style.ERROR('❌ FAILED')
                
        except Exception as e:
            return self.style.ERROR(f'❌ ERROR: {e}')

    def _test_redis(self):
        """Test Redis connection."""
        try:
            import redis
            from django.conf import settings
            import urllib.parse
            
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            url = urllib.parse.urlparse(redis_url)
            
            r = redis.Redis(
                host=url.hostname,
                port=url.port,
                db=url.path[1:] if url.path else 0,
                password=url.password,
                decode_responses=True
            )
            
            # Test connection
            r.ping()
            
            # Test set/get
            r.set('jobraker_test', 'test_value', ex=10)
            value = r.get('jobraker_test')
            
            if value == 'test_value':
                return self.style.SUCCESS('✅ WORKING')
            else:
                return self.style.ERROR('❌ FAILED')
                
        except Exception as e:
            return self.style.ERROR(f'❌ ERROR: {e}')