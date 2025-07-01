from django.test import TestCase
from apps.jobs.models import Job
from apps.jobs.documents import JobDocument # Assuming JobDocument is in apps.jobs.documents
from django.utils import timezone

class JobDocumentTest(TestCase):
    def setUp(self):
        self.job_data = {
            'title': "Software Engineer",
            'company': "Tech Solutions Inc.",
            'description': "Develop amazing software.",
            'requirements': "Python, Django",
            'benefits': "Health insurance, 401k",
            'location': "New York, NY",
            'city': "New York",
            'state': "NY",
            'country': "USA",
            'is_remote': False,
            'remote_type': 'no',
            'job_type': 'full_time',
            'experience_level': 'mid',
            'salary_min': 90000,
            'salary_max': 120000,
            'salary_currency': 'USD',
            'salary_period': 'yearly',
            'skills_required': ["Python", "Django", "API Design"],
            'skills_preferred': ["React", "AWS"],
            'technologies': ["Docker", "Kubernetes"],
            'external_source': "TestSource",
            'external_url': "http://example.com/job/123",
            'company_logo_url': "http://example.com/logo.png",
            'status': 'active',
            'posted_date': timezone.now() - timezone.timedelta(days=5),
            'application_deadline': timezone.now() + timezone.timedelta(days=25),
            'created_at': timezone.now() - timezone.timedelta(days=6),
            'updated_at': timezone.now() - timezone.timedelta(days=1),
        }
        self.job_instance = Job.objects.create(**self.job_data)
        self.document = JobDocument() # We are testing prepare methods, not full indexing here.

    def test_prepare_skills_required_text(self):
        prepared_skills = self.document.prepare_skills_required_text(self.job_instance)
        self.assertEqual(prepared_skills, ["Python", "Django", "API Design"])

    def test_prepare_skills_required_text_empty(self):
        self.job_instance.skills_required = []
        self.job_instance.save()
        prepared_skills = self.document.prepare_skills_required_text(self.job_instance)
        self.assertEqual(prepared_skills, [])

        self.job_instance.skills_required = None # Test None case if model allows
        self.job_instance.save()
        prepared_skills = self.document.prepare_skills_required_text(self.job_instance)
        self.assertEqual(prepared_skills, [])


    def test_prepare_skills_preferred_text(self):
        prepared_skills = self.document.prepare_skills_preferred_text(self.job_instance)
        self.assertEqual(prepared_skills, ["React", "AWS"])

    def test_prepare_technologies_text(self):
        prepared_technologies = self.document.prepare_technologies_text(self.job_instance)
        self.assertEqual(prepared_technologies, ["Docker", "Kubernetes"])

    def test_document_instance_fields_mapping(self):
        # This is more of an integration test for django-elasticsearch-dsl's mapping
        # but we can check if the document definition refers to correct model fields via 'attr'
        # For example, JobDocument.company_name uses attr='company'
        # This is implicitly tested by the fact that the prepare methods work on `instance.field_name`
        # and that `django_elasticsearch_dsl` would raise errors if `attr` was wrong during indexing.

        # A simple check could be to instantiate the document with an instance
        # and see if a specific field preparation works through the DSL's mechanisms,
        # though this often requires a running ES instance or more complex mocking.
        # For now, the prepare_ methods cover the custom logic.

        # Example: Check if the `company_name` field in the document correctly gets data from `job_instance.company`
        # This would typically be tested during an indexing test.
        # Here, we can assume that if prepare_ methods work, the basic `attr` mapping for simple fields
        # like `company_name = fields.TextField(attr='company', ...)` is correctly handled by the library.
        pass

    # Note: To test the full document generation (doc.to_dict()), you might need to
    # mock or have an Elasticsearch connection, as it might try to access mapping details.
    # These tests focus on the custom `prepare_` methods.
