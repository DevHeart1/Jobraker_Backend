import unittest
from unittest.mock import ANY, MagicMock, patch

from celery.exceptions import Retry  # To check if task retries

# We will be testing tasks from apps.integrations.tasks
# from apps.integrations import tasks as integration_tasks # Avoid direct import if tasks import models at module level


# Mock external services that the tasks use
class MockEmbeddingService:
    generate_embeddings = MagicMock()

    def __init__(self):
        self.embedding_model = "mock_embedding_model_name"  # For metric labels
        self.generate_embeddings.reset_mock()


class MockVectorDBService:
    search_similar_documents = MagicMock()

    def __init__(self):
        self.search_similar_documents.reset_mock()


# Mock OpenAI API client if tasks use it directly (they do for completion/moderation)
# We'll patch 'openai.ChatCompletion.create' and 'openai.Moderation.create' directly.

# Mock Django settings if tasks try to access settings.OPENAI_API_KEY etc.
# This can be done with @patch.object(settings, ...) or by setting up test settings.
# For simplicity, we'll assume tasks can get these or we mock them via settings patch.


class TestOpenAIRAGTasks(unittest.TestCase):

    def setUp(self):
        # Patch external services imported by apps.integrations.tasks
        self.patcher_embedding_service = patch(
            "apps.integrations.tasks.EmbeddingService",
            new_callable=lambda: MockEmbeddingService,
        )
        self.MockEmbeddingServiceClass = self.patcher_embedding_service.start()

        self.patcher_vdb_service = patch(
            "apps.integrations.tasks.VectorDBService",
            new_callable=lambda: MockVectorDBService,
        )
        self.MockVDBServiceClass = self.patcher_vdb_service.start()

        # Patch OpenAI API calls
        self.patcher_chat_completion = patch("openai.ChatCompletion.create")
        self.mock_openai_chat_completion_create = self.patcher_chat_completion.start()

        self.patcher_moderation = patch("openai.Moderation.create")
        self.mock_openai_moderation_create = self.patcher_moderation.start()

        # Patch settings if tasks directly access them for API keys/models
        # Example: self.patcher_settings = patch('apps.integrations.tasks.settings', MagicMock(OPENAI_API_KEY='fake_key', OPENAI_MODEL='gpt-test'))
        # self.mock_settings = self.patcher_settings.start()
        # For now, assume tasks get api_key and model name correctly or we handle it in each test.
        # It's better if tasks receive these as params or from a settings object that's easily mockable.
        # The tasks seem to do `from django.conf import settings; api_key = settings.OPENAI_API_KEY`
        # So, we need to patch `django.conf.settings` or use Django's test settings utilities.
        # Using override_settings from Django's test utilities is cleaner if this were a Django TestCase.
        # For unittest.TestCase, we patch where 'settings' is imported.

        self.patcher_django_settings = patch("apps.integrations.tasks.settings")
        self.mock_django_settings = self.patcher_django_settings.start()
        self.mock_django_settings.OPENAI_API_KEY = "test_openai_api_key"
        self.mock_django_settings.OPENAI_MODEL = "gpt-test-model"
        self.mock_django_settings.OPENAI_EMBEDDING_MODEL = "text-embedding-test"

        # Patch Prometheus metrics to check increments
        self.patcher_openai_calls_total = patch(
            "apps.integrations.tasks.OPENAI_API_CALLS_TOTAL"
        )
        self.mock_openai_calls_total = self.patcher_openai_calls_total.start()

        self.patcher_openai_call_duration = patch(
            "apps.integrations.tasks.OPENAI_API_CALL_DURATION_SECONDS"
        )
        self.mock_openai_call_duration = self.patcher_openai_call_duration.start()

        self.patcher_openai_moderation_checks = patch(
            "apps.integrations.tasks.OPENAI_MODERATION_CHECKS_TOTAL"
        )
        self.mock_openai_moderation_checks = (
            self.patcher_openai_moderation_checks.start()
        )

        self.patcher_openai_moderation_flagged = patch(
            "apps.integrations.tasks.OPENAI_MODERATION_FLAGGED_TOTAL"
        )
        self.mock_openai_moderation_flagged = (
            self.patcher_openai_moderation_flagged.start()
        )

        # Re-import tasks module here so it uses the patched versions of services/settings
        # This is crucial if tasks.py imports its dependencies at module level.
        global integration_tasks
        import importlib

        from apps.integrations import tasks as tasks_module

        importlib.reload(
            tasks_module
        )  # Reload to apply patches to module-level imports
        integration_tasks = tasks_module

    def tearDown(self):
        self.patcher_embedding_service.stop()
        self.patcher_vdb_service.stop()
        self.patcher_chat_completion.stop()
        self.patcher_moderation.stop()
        self.patcher_django_settings.stop()
        self.patcher_openai_calls_total.stop()
        self.patcher_openai_call_duration.stop()
        self.patcher_openai_moderation_checks.stop()
        self.patcher_openai_moderation_flagged.stop()

    # Test methods will be added here in subsequent steps.
    # For example:
    def test_get_openai_job_advice_task_with_rag_success(self):
        """Test get_openai_job_advice_task successfully uses RAG and calls OpenAI."""
        user_id = 1
        advice_type = "resume"
        context_query = "Help with my Python developer resume for fintech."
        mock_user_profile_data = {
            "experience_level": "Mid",
            "skills": ["python", "django"],
        }

        # Mock EmbeddingService
        mock_query_embedding = [
            0.1
        ] * 1536  # Standardized dimension from previous model
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.return_value = [
            mock_query_embedding
        ]

        # Mock VectorDBService
        mock_rag_doc1_text = (
            "Tip 1 for fintech resumes: highlight quantitative achievements."
        )
        mock_rag_doc2_text = "Tip 2: mention specific fintech regulations if relevant."
        mock_vdb_results = [
            {
                "text_content": mock_rag_doc1_text,
                "source_type": "career_article",
                "source_id": "article1",
                "similarity_score": 0.9,
            },
            {
                "text_content": mock_rag_doc2_text,
                "source_type": "career_article",
                "source_id": "article2",
                "similarity_score": 0.8,
            },
        ]
        self.MockVDBServiceClass.return_value.search_similar_documents.return_value = (
            mock_vdb_results
        )

        # Mock OpenAI ChatCompletion
        mock_ai_advice = "This is your AI generated resume advice enhanced with RAG."
        self.mock_openai_chat_completion_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_ai_advice))]
        )

        # Call the task directly
        result = integration_tasks.get_openai_job_advice_task(
            user_id,
            advice_type,
            context_query,
            user_profile_data=mock_user_profile_data,
            query_for_rag=context_query,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["advice"], mock_ai_advice)
        self.assertEqual(
            result["model_used"], "gpt-test-model"
        )  # From mock_django_settings

        # Verify EmbeddingService call
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.assert_called_once_with(
            [context_query]
        )

        # Verify VectorDBService call
        expected_rag_filter = {"source_type__in": ["career_article", "faq_item"]}
        self.MockVDBServiceClass.return_value.search_similar_documents.assert_called_once_with(
            query_embedding=mock_query_embedding,
            top_n=3,
            filter_criteria=expected_rag_filter,
        )

        # Verify OpenAI call (check that prompt includes RAG context)
        args, kwargs = self.mock_openai_chat_completion_create.call_args
        sent_messages = kwargs["messages"]
        self.assertIn(
            mock_rag_doc1_text, sent_messages[1]["content"]
        )  # User content prompt
        self.assertIn(mock_rag_doc2_text, sent_messages[1]["content"])
        self.assertIn(
            "--- Start of Retrieved Information ---", sent_messages[1]["content"]
        )

        # Verify metrics
        self.mock_openai_calls_total.labels(
            type="advice", model="gpt-test-model", status="success"
        ).inc.assert_called_once()
        self.mock_openai_call_duration.labels(
            type="advice", model="gpt-test-model"
        ).observe.assert_called_once()

    def test_get_openai_job_advice_task_no_rag_docs_found(self):
        user_id = 1
        advice_type = "interview"
        context_query = "Interview tips for a startup."

        self.MockEmbeddingServiceClass.return_value.generate_embeddings.return_value = [
            [0.1] * 1536
        ]
        self.MockVDBServiceClass.return_value.search_similar_documents.return_value = (
            []
        )  # No docs found

        mock_ai_advice = "Generic interview advice."
        self.mock_openai_chat_completion_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_ai_advice))]
        )

        result = integration_tasks.get_openai_job_advice_task(
            user_id, advice_type, context_query, query_for_rag=context_query
        )

        self.assertTrue(result["success"])
        args, kwargs = self.mock_openai_chat_completion_create.call_args
        sent_messages = kwargs["messages"]
        # Ensure RAG context markers are NOT in the prompt if no docs found
        self.assertNotIn(
            "--- Start of Retrieved Information ---", sent_messages[1]["content"]
        )

    def test_get_openai_job_advice_task_rag_embedding_fails(self):
        user_id = 1
        advice_type = "salary"
        context_query = "Salary negotiation."

        self.MockEmbeddingServiceClass.return_value.generate_embeddings.return_value = (
            None  # Embedding fails
        )

        mock_ai_advice = "Generic salary advice, no RAG."
        self.mock_openai_chat_completion_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_ai_advice))]
        )

        result = integration_tasks.get_openai_job_advice_task(
            user_id, advice_type, context_query, query_for_rag=context_query
        )

        self.assertTrue(result["success"])
        self.MockVDBServiceClass.return_value.search_similar_documents.assert_not_called()  # VDB search shouldn't happen
        args, kwargs = self.mock_openai_chat_completion_create.call_args
        sent_messages = kwargs["messages"]
        self.assertNotIn(
            "--- Start of Retrieved Information ---", sent_messages[1]["content"]
        )

    def test_get_openai_job_advice_task_openai_api_error(self):
        user_id = 1
        advice_type = "networking"
        context_query = "How to network effectively?"

        self.MockEmbeddingServiceClass.return_value.generate_embeddings.return_value = [
            [0.1] * 1536
        ]
        self.MockVDBServiceClass.return_value.search_similar_documents.return_value = []
        self.mock_openai_chat_completion_create.side_effect = Exception(
            "OpenAI API Error"
        )

        with self.assertRaises(Retry):  # Celery task should retry
            integration_tasks.get_openai_job_advice_task(
                user_id, advice_type, context_query, query_for_rag=context_query
            )

        self.mock_openai_calls_total.labels(
            type="advice", model="gpt-test-model", status="error"
        ).inc.assert_called_once()

    def test_get_openai_chat_response_task_with_rag_and_moderation_success(self):
        user_id = 1
        message = "Tell me about good jobs for python developers."
        mock_user_profile_data = {
            "experience_level": "Senior",
            "skills": ["python", "api_design"],
        }

        # Mock EmbeddingService for RAG query
        mock_query_embedding = [0.2] * 1536
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.return_value = [
            mock_query_embedding
        ]

        # Mock VectorDBService for RAG results
        mock_rag_job_text = "Found a Senior Python Developer role at AI Corp, focusing on API development."
        mock_vdb_results = [
            {
                "text_content": mock_rag_job_text,
                "source_type": "job_listing",
                "similarity_score": 0.88,
            }
        ]
        self.MockVDBServiceClass.return_value.search_similar_documents.return_value = (
            mock_vdb_results
        )

        # Mock Moderation API (input and output pass)
        self.mock_openai_moderation_create.side_effect = [
            MagicMock(results=[MagicMock(flagged=False)]),  # Input moderation
            MagicMock(results=[MagicMock(flagged=False)]),  # Output moderation
        ]

        # Mock OpenAI ChatCompletion
        mock_ai_chat_response = "Based on your profile and available roles, the Senior Python Developer at AI Corp seems like a great fit!"
        self.mock_openai_chat_completion_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_ai_chat_response))]
        )

        result = integration_tasks.get_openai_chat_response_task(
            user_id, message, user_profile_data=mock_user_profile_data
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["response"], mock_ai_chat_response)

        self.MockEmbeddingServiceClass.return_value.generate_embeddings.assert_called_once_with(
            [message]
        )
        expected_rag_filter = {
            "source_type": "job_listing"
        }  # Based on "jobs" in message
        self.MockVDBServiceClass.return_value.search_similar_documents.assert_called_once_with(
            query_embedding=mock_query_embedding,
            top_n=3,
            filter_criteria=expected_rag_filter,
        )

        # Check prompt includes RAG
        args, kwargs = self.mock_openai_chat_completion_create.call_args
        system_prompt = kwargs["messages"][0]["content"]
        self.assertIn(mock_rag_job_text, system_prompt)
        self.assertIn("--- Start of Retrieved Context ---", system_prompt)

        # Check moderation calls
        self.assertEqual(self.mock_openai_moderation_create.call_count, 2)
        self.mock_openai_moderation_create.assert_any_call(input=message)
        self.mock_openai_moderation_create.assert_any_call(input=mock_ai_chat_response)

        # Check metrics
        self.mock_openai_calls_total.labels(
            type="chat", model="gpt-test-model", status="success"
        ).inc.assert_called_once()
        self.mock_openai_call_duration.labels(
            type="chat", model="gpt-test-model"
        ).observe.assert_called_once()
        self.mock_openai_moderation_checks.labels(
            target="user_input"
        ).inc.assert_called_once()
        self.mock_openai_moderation_checks.labels(
            target="ai_output"
        ).inc.assert_called_once()
        self.mock_openai_moderation_flagged.labels(
            target="user_input"
        ).inc.assert_not_called()
        self.mock_openai_moderation_flagged.labels(
            target="ai_output"
        ).inc.assert_not_called()

    def test_get_openai_chat_response_task_input_flagged(self):
        user_id = 1
        flagged_message = "This is a flagged message."

        self.mock_openai_moderation_create.return_value = MagicMock(
            results=[MagicMock(flagged=True)]
        )

        result = integration_tasks.get_openai_chat_response_task(
            user_id, flagged_message
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "flagged_input")
        self.mock_openai_chat_completion_create.assert_not_called()  # OpenAI chat should not be called
        self.mock_openai_moderation_checks.labels(
            target="user_input"
        ).inc.assert_called_once()
        self.mock_openai_moderation_flagged.labels(
            target="user_input"
        ).inc.assert_called_once()

    def test_get_openai_chat_response_task_output_flagged(self):
        user_id = 1
        message = "A normal message."
        mock_flagged_ai_response = "This is a flagged AI response."

        self.MockEmbeddingServiceClass.return_value.generate_embeddings.return_value = [
            [0.1] * 1536
        ]
        self.MockVDBServiceClass.return_value.search_similar_documents.return_value = []

        self.mock_openai_moderation_create.side_effect = [
            MagicMock(results=[MagicMock(flagged=False)]),  # Input moderation passes
            MagicMock(results=[MagicMock(flagged=True)]),  # Output moderation flags
        ]
        self.mock_openai_chat_completion_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_flagged_ai_response))]
        )

        result = integration_tasks.get_openai_chat_response_task(user_id, message)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "flagged_output")
        self.mock_openai_chat_completion_create.assert_called_once()  # Chat was called
        self.mock_openai_moderation_checks.labels(
            target="ai_output"
        ).inc.assert_called_once()
        self.mock_openai_moderation_flagged.labels(
            target="ai_output"
        ).inc.assert_called_once()

    def test_analyze_openai_resume_task_with_rag_success(self):
        resume_text = "My resume..."
        target_job_description = (
            "Looking for a senior backend developer with Python and AWS."
        )
        mock_user_profile_data = {"experience_level": "Senior"}

        # Mock EmbeddingService for target_job RAG query
        mock_job_query_embedding = [0.3] * 1536
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.return_value = [
            mock_job_query_embedding
        ]

        # Mock VectorDBService for RAG results (resume advice articles)
        mock_resume_advice_text = (
            "For senior roles, emphasize leadership and system design."
        )
        mock_vdb_results = [
            {
                "text_content": mock_resume_advice_text,
                "source_type": "career_advice",
                "similarity_score": 0.92,
            }
        ]
        self.MockVDBServiceClass.return_value.search_similar_documents.return_value = (
            mock_vdb_results
        )

        # Mock OpenAI ChatCompletion
        mock_ai_analysis = (
            "This is your AI generated resume analysis, considering the advice found."
        )
        self.mock_openai_chat_completion_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_ai_analysis))]
        )

        result = integration_tasks.analyze_openai_resume_task(
            resume_text,
            target_job=target_job_description,
            user_profile_data=mock_user_profile_data,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["analysis"], mock_ai_analysis)

        # Verify EmbeddingService call for target_job
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.assert_called_once_with(
            [target_job_description]
        )

        # Verify VectorDBService call
        expected_rag_filter = {
            "source_type__in": ["career_advice", "faq_item", "interview_tips"],
            "metadata__category__icontains": "resume",
        }
        self.MockVDBServiceClass.return_value.search_similar_documents.assert_called_once_with(
            query_embedding=mock_job_query_embedding,
            top_n=2,
            filter_criteria=expected_rag_filter,
        )

        # Verify OpenAI call (check that prompt includes RAG context)
        args, kwargs = self.mock_openai_chat_completion_create.call_args
        sent_messages = kwargs["messages"]  # This task sends a single user prompt
        self.assertIn(
            mock_resume_advice_text, sent_messages[1]["content"]
        )  # User content prompt
        self.assertIn(
            "--- Start: Relevant Resume Writing Advice ---", sent_messages[1]["content"]
        )

        # Verify metrics
        self.mock_openai_calls_total.labels(
            type="resume_analysis", model="gpt-test-model", status="success"
        ).inc.assert_called_once()
        self.mock_openai_call_duration.labels(
            type="resume_analysis", model="gpt-test-model"
        ).observe.assert_called_once()

    def test_analyze_openai_resume_task_no_target_job_no_rag(self):
        resume_text = "My resume..."
        # No target_job, so RAG should be skipped

        mock_ai_analysis = "Generic resume analysis without specific job target."
        self.mock_openai_chat_completion_create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_ai_analysis))]
        )

        result = integration_tasks.analyze_openai_resume_task(
            resume_text, target_job=""
        )  # Empty target_job

        self.assertTrue(result["success"])
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.assert_not_called()
        self.MockVDBServiceClass.return_value.search_similar_documents.assert_not_called()

        args, kwargs = self.mock_openai_chat_completion_create.call_args
        sent_messages = kwargs["messages"]
        self.assertNotIn(
            "--- Start: Relevant Resume Writing Advice ---", sent_messages[1]["content"]
        )

    # Tests for RAG Content Ingestion Tasks
    @patch(
        "apps.integrations.tasks.Job"
    )  # Patch where Job model is imported by the task
    def test_generate_job_embeddings_and_ingest_for_rag_success(self, MockJobModel):
        job_id = str(uuid.uuid4())
        mock_job_instance = MagicMock(
            spec=MockJob
        )  # Use our existing MockJob for attributes
        mock_job_instance.id = job_id
        mock_job_instance.title = "Software Engineer"
        mock_job_instance.company = "TestCo"
        mock_job_instance.location = "TestCity"
        mock_job_instance.description = "A great job."
        mock_job_instance.job_type = "full_time"
        mock_job_instance.get_job_type_display.return_value = "Full Time"
        mock_job_instance.salary_min = 60000
        mock_job_instance.salary_max = 80000
        mock_job_instance.posted_date = None  # Or a mock datetime
        mock_job_instance.source = MagicMock(name="Adzuna")  # Mock related object
        mock_job_instance.external_id = "adz123"

        MockJobModel.objects.get.return_value = mock_job_instance

        mock_embeddings_dict = {
            "title_embedding": [0.4] * 1536,
            "combined_embedding": [0.5] * 1536,
        }
        self.MockEmbeddingServiceClass.return_value.generate_job_embeddings.return_value = (
            mock_embeddings_dict
        )

        # Mock VectorDBService methods
        mock_vdb_instance = self.MockVDBServiceClass.return_value
        mock_vdb_instance.delete_documents.return_value = True
        mock_vdb_instance.add_documents.return_value = True

        result = integration_tasks.generate_job_embeddings_and_ingest_for_rag(job_id)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["embeddings_saved_to_job"])
        self.assertTrue(result["rag_ingested"])

        MockJobModel.objects.get.assert_called_once_with(id=job_id)
        self.MockEmbeddingServiceClass.return_value.generate_job_embeddings.assert_called_once_with(
            mock_job_instance
        )
        mock_job_instance.save.assert_called_once_with(
            update_fields=["title_embedding", "combined_embedding"]
        )

        mock_vdb_instance.delete_documents.assert_called_once_with(
            source_type="job_listing", source_id=job_id
        )

        expected_rag_text_content = (
            f"Job Title: {mock_job_instance.title}\n"
            f"Company: {mock_job_instance.company}\n"
            f"Location: {mock_job_instance.location}\n"
            f"Type: {mock_job_instance.get_job_type_display()}\n"
            f"Description: {mock_job_instance.description}\n"
            f"Salary Range: ${mock_job_instance.salary_min} - ${mock_job_instance.salary_max}"
        )
        expected_metadata = {
            "job_id_original": job_id,
            "company": mock_job_instance.company,
            "location": mock_job_instance.location,
            "posted_date": None,  # Due to mock_job_instance.posted_date
            "job_type": mock_job_instance.job_type,
            "title": mock_job_instance.title,
        }
        mock_vdb_instance.add_documents.assert_called_once_with(
            texts=[expected_rag_text_content],
            embeddings=[mock_embeddings_dict["combined_embedding"]],
            source_types=["job_listing"],
            source_ids=[job_id],
            metadatas=[expected_metadata],
        )
        # Check relevant metrics
        self.mock_openai_calls_total.labels(
            type="embedding_job", model=ANY, status="success"
        ).inc.assert_called_once()

    @patch(
        "apps.integrations.tasks.KnowledgeArticle"
    )  # Patch where KnowledgeArticle is imported
    def test_process_knowledge_article_for_rag_task_active_article_success(
        self, MockKnowledgeArticleModel
    ):
        article_id = 1
        mock_article_instance = MagicMock()
        mock_article_instance.id = article_id
        mock_article_instance.is_active = True
        mock_article_instance.title = "Resume Tips"
        mock_article_instance.content = "Make your resume shine."
        mock_article_instance.source_type = "career_advice"
        mock_article_instance.category = "Resumes"
        mock_article_instance.get_tags_list.return_value = ["tips", "writing"]
        mock_article_instance.get_source_type_display.return_value = "Career Advice"
        MockKnowledgeArticleModel.objects.get.return_value = mock_article_instance

        mock_article_embedding = [0.6] * 1536
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.return_value = [
            mock_article_embedding
        ]

        mock_vdb_instance = self.MockVDBServiceClass.return_value
        mock_vdb_instance.delete_documents.return_value = True
        mock_vdb_instance.add_documents.return_value = True

        result = integration_tasks.process_knowledge_article_for_rag_task(article_id)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["rag_ingested"])

        MockKnowledgeArticleModel.objects.get.assert_called_once_with(id=article_id)
        expected_text_to_embed = f"Title: {mock_article_instance.title}\nContent: {mock_article_instance.content}"
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.assert_called_once_with(
            [expected_text_to_embed]
        )

        mock_vdb_instance.delete_documents.assert_called_once_with(
            source_type=mock_article_instance.source_type, source_id=str(article_id)
        )

        expected_metadata = {
            "article_id_original": str(article_id),
            "title": mock_article_instance.title,
            "category": mock_article_instance.category,
            "tags": ["tips", "writing"],
            "source_type_display": "Career Advice",
        }
        mock_vdb_instance.add_documents.assert_called_once_with(
            texts=[expected_text_to_embed],
            embeddings=[mock_article_embedding],
            source_types=[mock_article_instance.source_type],
            source_ids=[str(article_id)],
            metadatas=[expected_metadata],
        )
        self.mock_openai_calls_total.labels(
            type=f"embedding_knowledge_{mock_article_instance.source_type}",
            model=ANY,
            status="success",
        ).inc.assert_called_once()

    @patch("apps.integrations.tasks.KnowledgeArticle")
    def test_process_knowledge_article_for_rag_task_inactive_article_deletes_from_rag(
        self, MockKnowledgeArticleModel
    ):
        article_id = 2
        mock_article_instance = MagicMock()
        mock_article_instance.id = article_id
        mock_article_instance.is_active = False  # Key: inactive
        mock_article_instance.source_type = "faq"
        MockKnowledgeArticleModel.objects.get.return_value = mock_article_instance

        mock_vdb_instance = self.MockVDBServiceClass.return_value
        mock_vdb_instance.delete_documents.return_value = True

        result = integration_tasks.process_knowledge_article_for_rag_task(article_id)

        self.assertEqual(result["status"], "skipped_inactive_deleted")
        MockKnowledgeArticleModel.objects.get.assert_called_once_with(id=article_id)
        self.MockEmbeddingServiceClass.return_value.generate_embeddings.assert_not_called()
        mock_vdb_instance.delete_documents.assert_called_once_with(
            source_type="faq", source_id=str(article_id)
        )
        mock_vdb_instance.add_documents.assert_not_called()


if __name__ == "__main__":
    unittest.main()


# Test class for the new generate_interview_questions_task
class TestInterviewQuestionTasks(unittest.TestCase):
    def setUp(self):
        # Patch Job model lookup
        self.patcher_job_model = patch("apps.integrations.tasks.Job")
        self.MockJobModel = self.patcher_job_model.start()
        self.mock_job_instance = MagicMock()
        self.MockJobModel.objects.get.return_value = self.mock_job_instance

        # Patch UserProfile model lookup (optional, if user_id is used)
        self.patcher_user_profile_model = patch("apps.integrations.tasks.UserProfile")
        self.MockUserProfileModel = self.patcher_user_profile_model.start()
        self.mock_user_profile_instance = MagicMock()
        self.MockUserProfileModel.objects.get.return_value = (
            self.mock_user_profile_instance
        )

        # Patch OpenAIClient
        self.patcher_openai_client = patch("apps.integrations.tasks.OpenAIClient")
        self.MockOpenAIClientClass = self.patcher_openai_client.start()
        self.mock_openai_client_instance = self.MockOpenAIClientClass.return_value
        # Assume OpenAIClient has a 'model' attribute for metrics
        self.mock_openai_client_instance.model = "gpt-test-interviewer"

        # Patch Prometheus metrics
        self.patcher_openai_calls_total_it = patch(
            "apps.integrations.tasks.OPENAI_API_CALLS_TOTAL"
        )
        self.mock_openai_calls_total_it = self.patcher_openai_calls_total_it.start()
        self.patcher_openai_call_duration_it = patch(
            "apps.integrations.tasks.OPENAI_API_CALL_DURATION_SECONDS"
        )
        self.mock_openai_call_duration_it = self.patcher_openai_call_duration_it.start()

        # Reload tasks module to ensure it uses our patched versions
        # This is important if tasks.py imports these at the module level
        global integration_tasks
        import importlib

        from apps.integrations import tasks as tasks_module

        importlib.reload(tasks_module)
        integration_tasks = tasks_module

    def tearDown(self):
        self.patcher_job_model.stop()
        self.patcher_user_profile_model.stop()
        self.patcher_openai_client.stop()
        self.patcher_openai_calls_total_it.stop()
        self.patcher_openai_call_duration_it.stop()

    def test_generate_interview_questions_task_success(self):
        job_id = "test_job_uuid"
        user_id_for_task = (
            "test_user_uuid"  # Can be None if not testing personalization
        )

        self.mock_job_instance.id = job_id
        self.mock_job_instance.title = "Senior Developer"
        self.mock_job_instance.description = "Requires Python and Django skills."

        # Mock UserProfile data if user_id is passed
        self.mock_user_profile_instance.current_title = "Software Engineer"
        self.mock_user_profile_instance.get_experience_level_display.return_value = (
            "Mid Level"
        )
        self.mock_user_profile_instance.skills = [
            "Python",
            "API",
            "JavaScript",
            "SQL",
            "Docker",
            "Kubernetes",
        ]  # More than 5
        self.mock_user_profile_instance.bio = (
            "A passionate developer building cool things."
        )

        expected_questions = [
            {"type": "Technical", "question": "Explain Django's ORM."}
        ]
        self.mock_openai_client_instance.generate_interview_questions.return_value = (
            expected_questions
        )

        result = integration_tasks.generate_interview_questions_task(
            job_id=job_id, user_id=user_id_for_task
        )

        self.MockJobModel.objects.get.assert_called_once_with(id=job_id)
        if user_id_for_task:
            self.MockUserProfileModel.objects.get.assert_called_once_with(
                user_id=user_id_for_task
            )
            expected_profile_summary_parts = [
                "Current Title: Software Engineer",
                "Experience Level: Mid Level",
                "Key Skills: Python, API, JavaScript, SQL, Docker",  # Top 5
                f"Bio Snippet: {self.mock_user_profile_instance.bio[:200]}...",
            ]
            expected_summary = ". ".join(expected_profile_summary_parts)
        else:
            expected_summary = None
            self.MockUserProfileModel.objects.get.assert_not_called()

        self.mock_openai_client_instance.generate_interview_questions.assert_called_once_with(
            job_title=self.mock_job_instance.title,
            job_description=self.mock_job_instance.description,
            user_profile_summary=expected_summary,  # Will be None if user_id_for_task is None
        )

        self.assertEqual(result["job_id"], job_id)
        self.assertEqual(result["job_title"], self.mock_job_instance.title)
        self.assertEqual(result["questions"], expected_questions)
        self.assertEqual(result["status"], "success")

        self.mock_openai_calls_total_it.labels(
            type="interview_question_generation",
            model=self.mock_openai_client_instance.model,
            status="success",
        ).inc.assert_called_once()
        self.mock_openai_call_duration_it.labels(
            type="interview_question_generation",
            model=self.mock_openai_client_instance.model,
        ).observe.assert_called_once()

    def test_generate_interview_questions_task_job_not_found(self):
        self.MockJobModel.objects.get.side_effect = (
            self.MockJobModel.DoesNotExist
        )  # Simulate Job.DoesNotExist

        result = integration_tasks.generate_interview_questions_task(
            job_id="non_existent_job_id"
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Job not found")
        self.mock_openai_client_instance.generate_interview_questions.assert_not_called()
        # Metrics should not be incremented for API call if it didn't happen
        self.mock_openai_calls_total_it.labels().inc.assert_not_called()

    def test_generate_interview_questions_task_openai_client_fails(self):
        job_id = "another_job_uuid"
        self.mock_job_instance.id = job_id
        self.mock_job_instance.title = "QA Engineer"
        self.mock_job_instance.description = "Test software."

        self.mock_openai_client_instance.generate_interview_questions.side_effect = (
            Exception("OpenAI Client Error")
        )

        with self.assertRaises(Retry):  # Expect Celery to retry
            integration_tasks.generate_interview_questions_task(
                job_id=job_id, user_id=None
            )

        # Check metrics for error status
        self.mock_openai_calls_total_it.labels(
            type="interview_question_generation",
            model=self.mock_openai_client_instance.model,
            status="error",
        ).inc.assert_called_once()
        self.mock_openai_call_duration_it.labels(
            type="interview_question_generation",
            model=self.mock_openai_client_instance.model,
        ).observe.assert_called_once()

    def test_generate_interview_questions_task_no_user_profile_found(self):
        job_id = "job_with_user_no_profile"
        user_id_no_profile = "user_no_profile_uuid"

        self.mock_job_instance.id = job_id
        self.mock_job_instance.title = "Analyst"
        self.mock_job_instance.description = "Analyze things."

        self.MockUserProfileModel.objects.get.side_effect = (
            self.MockUserProfileModel.DoesNotExist
        )

        expected_questions = [{"type": "General", "question": "Why this role?"}]
        self.mock_openai_client_instance.generate_interview_questions.return_value = (
            expected_questions
        )

        result = integration_tasks.generate_interview_questions_task(
            job_id=job_id, user_id=user_id_no_profile
        )

        self.MockUserProfileModel.objects.get.assert_called_once_with(
            user_id=user_id_no_profile
        )
        # Ensure client was called with user_profile_summary=None
        self.mock_openai_client_instance.generate_interview_questions.assert_called_once_with(
            job_title=self.mock_job_instance.title,
            job_description=self.mock_job_instance.description,
            user_profile_summary=None,
        )
        self.assertEqual(result["status"], "success")  # Task should still succeed
        self.assertEqual(result["questions"], expected_questions)


class MockApplication:
    objects = MagicMock()

    def __init__(self, id, skyvern_task_id=None, status="pending", **kwargs):
        self.id = id
        self.skyvern_task_id = skyvern_task_id
        self.status = status
        self.skyvern_response_data = None
        self.applied_at = None
        for key, value in kwargs.items():
            setattr(self, key, value)

    def save(self, update_fields=None):  # Mock save
        pass


class TestSkyvernTasks(unittest.TestCase):
    def setUp(self):
        # Patch SkyvernAPIClient where it's imported by apps.integrations.tasks
        self.patcher_skyvern_client = patch(
            "apps.integrations.tasks.SkyvernAPIClient", autospec=True
        )
        self.MockSkyvernAPIClientClass = self.patcher_skyvern_client.start()
        self.mock_skyvern_client_instance = self.MockSkyvernAPIClientClass.return_value

        # Patch Application model
        self.patcher_application_model = patch(
            "apps.integrations.tasks.Application", new_callable=lambda: MockApplication
        )
        self.MockApplicationModel = self.patcher_application_model.start()
        self.MockApplicationModel.objects = MagicMock()  # Mock the manager
        self.MockApplicationModel.DoesNotExist = classmethod(
            lambda cls: type("DoesNotExist", (Exception,), {})
        )()

        # Patch Prometheus metrics for Skyvern submissions
        self.patcher_skyvern_submissions_total = patch(
            "apps.integrations.tasks.SKYVERN_APPLICATION_SUBMISSIONS_TOTAL"
        )
        self.mock_skyvern_submissions_total = (
            self.patcher_skyvern_submissions_total.start()
        )

        # Patch timezone.now for predictable applied_at
        self.patcher_timezone_now = patch("apps.integrations.tasks.timezone.now")
        self.mock_timezone_now = self.patcher_timezone_now.start()
        self.mock_timezone_now.return_value = "mocked_datetime_now"

        # Reload tasks module to ensure it uses our patched versions
        global integration_tasks
        import importlib

        from apps.integrations import tasks as tasks_module

        importlib.reload(tasks_module)
        integration_tasks = tasks_module

    def tearDown(self):
        self.patcher_skyvern_client.stop()
        self.patcher_application_model.stop()
        self.patcher_skyvern_submissions_total.stop()
        self.patcher_timezone_now.stop()

    def test_submit_skyvern_application_task_success(self):
        app_id = str(uuid.uuid4())
        job_url = "http://example.com/job/123"
        prompt_template = "Apply to {job_url}"
        user_profile_data = {"name": "Test User"}

        mock_app_instance = MockApplication(id=app_id)
        self.MockApplicationModel.objects.get.return_value = mock_app_instance

        self.mock_skyvern_client_instance.run_task.return_value = {
            "task_id": "sky_123",
            "status": "PENDING",
        }

        result = integration_tasks.submit_skyvern_application_task(
            app_id, job_url, prompt_template, user_profile_data
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["skyvern_task_id"], "sky_123")
        self.MockApplicationModel.objects.get.assert_called_once_with(id=app_id)
        self.mock_skyvern_client_instance.run_task.assert_called_once()
        self.assertEqual(mock_app_instance.skyvern_task_id, "sky_123")
        self.assertEqual(mock_app_instance.status, "submitting_via_skyvern")
        # Check that save was called with specific fields
        mock_app_instance.save.assert_called_once_with(
            update_fields=["skyvern_task_id", "status", "updated_at"]
        )
        self.mock_skyvern_submissions_total.labels(
            status="initiated"
        ).inc.assert_called_once()

    def test_submit_skyvern_application_task_app_not_found(self):
        self.MockApplicationModel.objects.get.side_effect = (
            self.MockApplicationModel.DoesNotExist
        )

        result = integration_tasks.submit_skyvern_application_task(
            "nonexistent_app_id", "url", "prompt", {}
        )
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Application not found")
        self.mock_skyvern_client_instance.run_task.assert_not_called()
        self.mock_skyvern_submissions_total.labels(
            status="application_not_found"
        ).inc.assert_called_once()

    def test_submit_skyvern_application_task_skyvern_api_fails_to_create_task(self):
        app_id = str(uuid.uuid4())
        mock_app_instance = MockApplication(id=app_id)
        self.MockApplicationModel.objects.get.return_value = mock_app_instance
        self.mock_skyvern_client_instance.run_task.return_value = (
            None  # Skyvern API call failed
        )

        result = integration_tasks.submit_skyvern_application_task(
            app_id, "url", "prompt", {}
        )

        self.assertEqual(result["status"], "failure")
        self.assertEqual(mock_app_instance.status, "skyvern_submission_failed")
        mock_app_instance.save.assert_called_once_with(
            update_fields=["status", "skyvern_response_data", "updated_at"]
        )
        self.mock_skyvern_submissions_total.labels(
            status="creation_failed"
        ).inc.assert_called_once()

    def test_check_skyvern_task_status_task_completed(self):
        skyvern_task_id = "sky_123"
        app_id = str(uuid.uuid4())
        mock_app_instance = MockApplication(id=app_id, skyvern_task_id=skyvern_task_id)
        self.MockApplicationModel.objects.get.return_value = mock_app_instance
        self.mock_skyvern_client_instance.get_task_status.return_value = {
            "status": "COMPLETED"
        }

        # Mock the .delay() method of the task we are going to call
        with patch(
            "apps.integrations.tasks.retrieve_skyvern_task_results_task.delay"
        ) as mock_retrieve_delay:
            result = integration_tasks.check_skyvern_task_status_task(
                skyvern_task_id, app_id
            )

        self.assertEqual(result["skyvern_status"], "COMPLETED")
        self.assertEqual(mock_app_instance.status, "submitted")
        self.assertEqual(mock_app_instance.applied_at, "mocked_datetime_now")
        mock_app_instance.save.assert_called_once_with(
            update_fields=["status", "updated_at", "applied_at"]
        )
        self.mock_skyvern_submissions_total.labels(
            status="completed_success"
        ).inc.assert_called_once()
        mock_retrieve_delay.assert_called_once_with(skyvern_task_id, app_id)

    def test_check_skyvern_task_status_task_failed(self):
        skyvern_task_id = "sky_456"
        app_id = str(uuid.uuid4())
        mock_app_instance = MockApplication(id=app_id, skyvern_task_id=skyvern_task_id)
        self.MockApplicationModel.objects.get.return_value = mock_app_instance
        skyvern_api_response = {
            "status": "FAILED",
            "error_details": "Some error from Skyvern",
        }
        self.mock_skyvern_client_instance.get_task_status.return_value = (
            skyvern_api_response
        )

        result = integration_tasks.check_skyvern_task_status_task(
            skyvern_task_id, app_id
        )

        self.assertEqual(result["skyvern_status"], "FAILED")
        self.assertEqual(mock_app_instance.status, "skyvern_submission_failed")
        self.assertEqual(mock_app_instance.skyvern_response_data, skyvern_api_response)
        mock_app_instance.save.assert_called_once_with(
            update_fields=["status", "updated_at", "skyvern_response_data"]
        )
        self.mock_skyvern_submissions_total.labels(
            status="failed"
        ).inc.assert_called_once()

    def test_check_skyvern_task_status_app_not_found(self):
        self.MockApplicationModel.objects.get.side_effect = (
            self.MockApplicationModel.DoesNotExist
        )
        result = integration_tasks.check_skyvern_task_status_task("sky_id", "app_id")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Application for Skyvern task not found")
        self.mock_skyvern_submissions_total.labels(
            status="check_app_not_found"
        ).inc.assert_called_once()

    def test_check_skyvern_task_status_task_skyvern_canceled(self):
        skyvern_task_id = "sky_canceled_789"
        app_id = str(uuid.uuid4())
        mock_app_instance = MockApplication(id=app_id, skyvern_task_id=skyvern_task_id)
        self.MockApplicationModel.objects.get.return_value = mock_app_instance
        skyvern_api_response = {"status": "CANCELED", "reason": "User request"}
        self.mock_skyvern_client_instance.get_task_status.return_value = (
            skyvern_api_response
        )

        result = integration_tasks.check_skyvern_task_status_task(
            skyvern_task_id, app_id
        )

        self.assertEqual(result["skyvern_status"], "CANCELED")
        self.assertEqual(mock_app_instance.status, "skyvern_canceled")
        self.assertEqual(mock_app_instance.skyvern_response_data, skyvern_api_response)
        mock_app_instance.save.assert_called_once_with(
            update_fields=["status", "updated_at", "skyvern_response_data"]
        )
        self.mock_skyvern_submissions_total.labels(
            status="canceled"
        ).inc.assert_called_once()

    def test_check_skyvern_task_status_task_skyvern_requires_attention(self):
        skyvern_task_id = "sky_attention_101"
        app_id = str(uuid.uuid4())
        mock_app_instance = MockApplication(id=app_id, skyvern_task_id=skyvern_task_id)
        self.MockApplicationModel.objects.get.return_value = mock_app_instance
        skyvern_api_response = {
            "status": "REQUIRES_ATTENTION",
            "details": "CAPTCHA detected",
        }
        self.mock_skyvern_client_instance.get_task_status.return_value = (
            skyvern_api_response
        )

        result = integration_tasks.check_skyvern_task_status_task(
            skyvern_task_id, app_id
        )

        self.assertEqual(result["skyvern_status"], "REQUIRES_ATTENTION")
        self.assertEqual(mock_app_instance.status, "skyvern_requires_attention")
        self.assertEqual(mock_app_instance.skyvern_response_data, skyvern_api_response)
        mock_app_instance.save.assert_called_once_with(
            update_fields=["status", "updated_at", "skyvern_response_data"]
        )
        self.mock_skyvern_submissions_total.labels(
            status="requires_attention"
        ).inc.assert_called_once()

    def test_check_skyvern_task_status_task_skyvern_pending(self):
        skyvern_task_id = "sky_pending_112"
        app_id = str(uuid.uuid4())
        # Start with a different status to see if it changes to 'submitting_via_skyvern'
        mock_app_instance = MockApplication(
            id=app_id, skyvern_task_id=skyvern_task_id, status="pending"
        )
        self.MockApplicationModel.objects.get.return_value = mock_app_instance
        self.mock_skyvern_client_instance.get_task_status.return_value = {
            "status": "PENDING"
        }

        result = integration_tasks.check_skyvern_task_status_task(
            skyvern_task_id, app_id
        )

        self.assertEqual(result["skyvern_status"], "PENDING")
        self.assertEqual(
            mock_app_instance.status, "submitting_via_skyvern"
        )  # Should update if not already this
        mock_app_instance.save.assert_called_once_with(
            update_fields=["status", "updated_at"]
        )
        # No specific submission total metric change for PENDING/RUNNING after initial 'initiated'

    def test_retrieve_skyvern_task_results_task_success(self):
        skyvern_task_id = "sky_789"
        app_id = str(uuid.uuid4())
        mock_app_instance = MockApplication(id=app_id, skyvern_task_id=skyvern_task_id)
        self.MockApplicationModel.objects.get.return_value = mock_app_instance

        results_payload = {
            "data": {"confirmation_id": "conf_123"},
            "status": "COMPLETED",
        }
        self.mock_skyvern_client_instance.get_task_results.return_value = (
            results_payload
        )

        result = integration_tasks.retrieve_skyvern_task_results_task(
            skyvern_task_id, app_id
        )

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["results_fetched"])
        self.assertEqual(mock_app_instance.skyvern_response_data, results_payload)
        # Status should remain 'submitted' if already set by check_status, or updated if results say FAILED
        # Current logic updates status if results say FAILED and current status is not already failed.
        self.assertEqual(
            mock_app_instance.status, "submitted"
        )  # Assuming it was 'submitted'
        mock_app_instance.save.assert_called_once_with(
            update_fields=["skyvern_response_data", "status", "updated_at"]
        )

    def test_retrieve_skyvern_task_results_task_api_returns_none(self):
        skyvern_task_id = "sky_000"
        app_id = str(uuid.uuid4())
        mock_app_instance = MockApplication(id=app_id, skyvern_task_id=skyvern_task_id)
        self.MockApplicationModel.objects.get.return_value = mock_app_instance
        self.mock_skyvern_client_instance.get_task_results.return_value = (
            None  # API call failed or no data
        )

        result = integration_tasks.retrieve_skyvern_task_results_task(
            skyvern_task_id, app_id
        )

        self.assertEqual(result["status"], "no_results_data")
        self.assertEqual(
            mock_app_instance.skyvern_response_data,
            {"info": "Results retrieval attempted, no data returned by Skyvern."},
        )
        mock_app_instance.save.assert_called_once_with(
            update_fields=["skyvern_response_data", "updated_at"]
        )


if __name__ == "__main__":
    unittest.main()
