from django.conf import settings
from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry

from .models import Job

# Get Elasticsearch index name from settings, with a default
JOB_INDEX_NAME = getattr(settings, "ELASTICSEARCH_JOB_INDEX_NAME", "jobraker-jobs")


@registry.register_document
class JobDocument(Document):
    # Define common text field settings with an English analyzer
    english_text_field = fields.TextField(
        analyzer="english",
        fields={"raw": fields.KeywordField()},  # For exact matches or aggregations
    )

    title = english_text_field
    company_name = fields.TextField(  # Using a different name to avoid conflict with 'company' object if Job model had FK
        attr="company",  # Maps to Job.company field
        analyzer="english",
        fields={"raw": fields.KeywordField()},
    )
    description = fields.TextField(analyzer="english")
    requirements = fields.TextField(
        analyzer="english", required=False
    )  # Mark as not required if blank=True in model
    benefits = fields.TextField(analyzer="english", required=False)

    location_text = fields.TextField(  # For full-text search on location string
        attr="location", analyzer="english", fields={"raw": fields.KeywordField()}
    )
    city = fields.KeywordField()
    state = fields.KeywordField()
    country = fields.KeywordField()
    is_remote = fields.BooleanField()
    remote_type = fields.KeywordField()

    job_type = fields.KeywordField()
    experience_level = fields.KeywordField()

    salary_min = fields.IntegerField(required=False)
    salary_max = fields.IntegerField(required=False)
    salary_currency = fields.KeywordField(required=False)
    salary_period = fields.KeywordField(required=False)

    # For JSONFields skills_required, skills_preferred, technologies:
    # We can index them as list of keywords or as a single text field.
    # Using TextField here to make them searchable as text, can also use KeywordField for exact matches.
    skills_required_text = fields.TextField(
        analyzer="english", multi=True
    )  # 'multi=True' for lists of strings
    skills_preferred_text = fields.TextField(analyzer="english", multi=True)
    technologies_text = fields.TextField(analyzer="english", multi=True)

    external_source = fields.KeywordField(required=False)
    external_url = fields.KeywordField(
        required=False
    )  # Keyword if not searching within URL, Text if so
    company_logo_url = fields.KeywordField(required=False)

    status = fields.KeywordField()  # Job status like 'active', 'closed'
    posted_date = fields.DateField(required=False)
    application_deadline = fields.DateField(required=False)

    created_at = fields.DateField()  # For sorting by creation if needed
    updated_at = fields.DateField()

    class Index:
        # Name of the Elasticsearch index
        name = JOB_INDEX_NAME
        # See Elasticsearch Indices API reference for available settings
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,  # For local dev; adjust for production
        }

    class Django:
        model = Job  # The model associated with this Document

        # The fields of the model you want to be indexed in Elasticsearch
        fields = [
            # Fields directly mapped are listed above.
            # If a field is not explicitly defined above but listed here,
            # django-elasticsearch-dsl will try to auto-map it.
            # It's usually better to define them explicitly for control.
            # We've defined most relevant fields explicitly.
            # 'id' is usually mapped automatically as meta field.
        ]
        # Optional: Paginate the queryset used to build the index
        # queryset_pagination = 5000

    # Methods to prepare data for complex fields (like JSONField)
    def prepare_skills_required_text(self, instance):
        if instance.skills_required and isinstance(instance.skills_required, list):
            return [str(skill) for skill in instance.skills_required if skill]
        return []

    def prepare_skills_preferred_text(self, instance):
        if instance.skills_preferred and isinstance(instance.skills_preferred, list):
            return [str(skill) for skill in instance.skills_preferred if skill]
        return []

    def prepare_technologies_text(self, instance):
        if instance.technologies and isinstance(instance.technologies, list):
            return [str(tech) for tech in instance.technologies if tech]
        return []

    # Example: If you wanted to index a calculated property from the model
    # def prepare_salary_range_display_es(self, instance):
    #     return instance.salary_range_display # Assuming salary_range_display is a property on Job model

    # Note: Ensure that the 'attr' in fields.TextField(attr='company') matches the model field name
    # if the document field name is different (like 'company_name' for model's 'company' field).
    # If document field name is same as model field, 'attr' is not needed. Example: title = english_text_field

    # To make a field not indexed but still part of _source (e.g. for display from ES result):
    # my_non_indexed_field = fields.ObjectField(enabled=False) # or other appropriate field type
    # This is useful if you want ES to return the data but don't need to search/filter on it.
    # For most fields here, we want them searchable/filterable.
