import json
from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.conf import settings

# Assuming your OpenAIClient is in the path below
from apps.integrations.services.openai import OpenAIClient


class OpenAIClientInterviewQuestionsTest(TestCase):

    def setUp(self):
        # Configure minimal settings if Django settings are not fully loaded
        if not settings.configured:
            settings.configure(
                OPENAI_API_KEY="test_api_key_for_client"
            )  # Ensure API key is set for _validate_api_key

        self.client = OpenAIClient()
        # Ensure the client's api_key attribute is set if it relies on Django settings post-init
        # or if settings were not configured before __init__ was called by another import.
        if not self.client.api_key:
            self.client.api_key = "test_api_key_for_client"

    @patch("apps.integrations.services.openai.openai.chat.completions.create")
    def test_generate_interview_questions_success_json_parsing(
        self, mock_openai_create
    ):
        job_title = "Software Engineer"
        job_description = "Develop and maintain web applications."
        expected_questions = [
            {"type": "Technical", "question": "Explain SOLID principles."},
            {
                "type": "Behavioral",
                "question": "Describe a time you overcame a technical challenge.",
            },
        ]

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(
            expected_questions
        )  # Perfect JSON response
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai_create.return_value = mock_response

        questions = self.client.generate_interview_questions(job_title, job_description)

        self.assertEqual(questions, expected_questions)
        mock_openai_create.assert_called_once()
        call_args = mock_openai_create.call_args[1]  # kwargs
        self.assertIn(job_title, call_args["system_prompt"])
        self.assertIn(job_description, call_args["system_prompt"])
        self.assertIn(
            "Return your response as a JSON list of objects", call_args["system_prompt"]
        )
        self.assertEqual(call_args["messages"][0]["role"], "user")

    @patch("apps.integrations.services.openai.openai.chat.completions.create")
    def test_generate_interview_questions_with_leading_trailing_text_json_parsing(
        self, mock_openai_create
    ):
        job_title = "QA Analyst"
        job_description = "Ensure software quality."
        json_questions_str = json.dumps(
            [
                {
                    "type": "Situational",
                    "question": "How do you handle bugs found late in cycle?",
                }
            ]
        )

        mock_choice = MagicMock()
        mock_choice.message.content = f"Sure, here are the questions:\n{json_questions_str}\nLet me know if you need more."
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai_create.return_value = mock_response

        questions = self.client.generate_interview_questions(job_title, job_description)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["type"], "Situational")
        self.assertEqual(
            questions[0]["question"], "How do you handle bugs found late in cycle?"
        )

    @patch("apps.integrations.services.openai.openai.chat.completions.create")
    def test_generate_interview_questions_invalid_json_structure(
        self, mock_openai_create
    ):
        job_title = "Product Manager"
        job_description = "Define product vision."
        # JSON is valid, but not a list of {"type": ..., "question": ...}
        invalid_json_questions_str = json.dumps(
            {"error": "bad format", "data": "some question here"}
        )

        mock_choice = MagicMock()
        mock_choice.message.content = invalid_json_questions_str
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai_create.return_value = mock_response

        questions = self.client.generate_interview_questions(job_title, job_description)

        # Fallback behavior: returns list with one item containing the raw response
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["type"], "general")
        self.assertEqual(questions[0]["question"], invalid_json_questions_str)

    @patch("apps.integrations.services.openai.openai.chat.completions.create")
    def test_generate_interview_questions_non_json_response(self, mock_openai_create):
        job_title = "Designer"
        job_description = "Create beautiful interfaces."
        plain_text_response = "What is your design philosophy?"

        mock_choice = MagicMock()
        mock_choice.message.content = plain_text_response
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai_create.return_value = mock_response

        questions = self.client.generate_interview_questions(job_title, job_description)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["type"], "general")
        self.assertEqual(questions[0]["question"], plain_text_response)

    @patch("apps.integrations.services.openai.openai.chat.completions.create")
    def test_generate_interview_questions_empty_response_string(
        self, mock_openai_create
    ):
        job_title = "Analyst"
        job_description = "Analyze data."

        mock_choice = MagicMock()
        mock_choice.message.content = "  "  # Empty or whitespace only
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai_create.return_value = mock_response

        questions = self.client.generate_interview_questions(job_title, job_description)
        self.assertEqual(questions, [])

    @patch("apps.integrations.services.openai.openai.chat.completions.create")
    def test_generate_interview_questions_openai_api_error(self, mock_openai_create):
        mock_openai_create.side_effect = Exception("OpenAI API Error")

        job_title = "Data Scientist"
        job_description = "Build ML models."
        questions = self.client.generate_interview_questions(job_title, job_description)

        self.assertEqual(questions, [])  # Should return empty list on API error

    def test_generate_interview_questions_no_api_key(self):
        original_api_key = self.client.api_key
        self.client.api_key = None  # Simulate no API key

        with self.assertRaises(
            ValueError
        ) as context:  # _validate_api_key raises ValueError
            self.client.generate_interview_questions("Test", "Test desc")
        self.assertTrue("OpenAI API key not configured" in str(context.exception))

        self.client.api_key = original_api_key  # Restore API key

    @patch("apps.integrations.services.openai.openai.chat.completions.create")
    def test_prompt_includes_user_profile_if_provided(self, mock_openai_create):
        job_title = "Software Engineer"
        job_description = "Develop and maintain web applications."
        user_profile_summary = "Experienced Python developer with 5 years in Django."

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(
            [{"type": "Technical", "question": "Explain Django ORM."}]
        )
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_openai_create.return_value = mock_response

        self.client.generate_interview_questions(
            job_title, job_description, user_profile_summary=user_profile_summary
        )

        mock_openai_create.assert_called_once()
        call_args = mock_openai_create.call_args[1]
        self.assertIn(user_profile_summary, call_args["system_prompt"])
        self.assertIn("CANDIDATE PROFILE START", call_args["system_prompt"])
