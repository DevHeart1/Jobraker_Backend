"""
Management command to test external API integrations.
"""

import json

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.integrations.services.config_service import APIConfigurationService


class Command(BaseCommand):
    help = "Test external API integrations (OpenAI, Adzuna, Skyvern)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--quick",
            action="store_true",
            help="Run quick configuration check without API calls",
        )
        parser.add_argument(
            "--api",
            type=str,
            choices=["openai", "adzuna", "skyvern"],
            help="Test specific API only",
        )
        parser.add_argument(
            "--json", action="store_true", help="Output results in JSON format"
        )

    def handle(self, *args, **options):
        config_service = APIConfigurationService()

        if options["quick"]:
            self.run_quick_check(config_service, options)
        elif options["api"]:
            self.run_specific_api_test(config_service, options["api"], options)
        else:
            self.run_full_test(config_service, options)

    def run_quick_check(self, config_service, options):
        """Run quick configuration check without API calls."""
        self.stdout.write(self.style.SUCCESS("Running quick configuration check..."))

        results = {
            "openai": {
                "configured": bool(config_service.openai_api_key),
                "api_key_length": (
                    len(config_service.openai_api_key)
                    if config_service.openai_api_key
                    else 0
                ),
            },
            "adzuna": {
                "configured": bool(
                    config_service.adzuna_app_id and config_service.adzuna_api_key
                ),
                "app_id_length": (
                    len(config_service.adzuna_app_id)
                    if config_service.adzuna_app_id
                    else 0
                ),
                "api_key_length": (
                    len(config_service.adzuna_api_key)
                    if config_service.adzuna_api_key
                    else 0
                ),
            },
            "skyvern": {
                "configured": bool(config_service.skyvern_api_key),
                "api_key_length": (
                    len(config_service.skyvern_api_key)
                    if config_service.skyvern_api_key
                    else 0
                ),
                "base_url": config_service.skyvern_base_url,
            },
        }

        if options["json"]:
            self.stdout.write(json.dumps(results, indent=2))
        else:
            self.display_quick_results(results)

    def run_specific_api_test(self, config_service, api_name, options):
        """Test a specific API."""
        self.stdout.write(self.style.SUCCESS(f"Testing {api_name.upper()} API..."))

        if api_name == "openai":
            result = config_service.check_openai_api()
        elif api_name == "adzuna":
            result = config_service.check_adzuna_api()
        elif api_name == "skyvern":
            result = config_service.check_skyvern_api()

        if options["json"]:
            self.stdout.write(json.dumps({api_name: result}, indent=2))
        else:
            self.display_api_result(api_name, result)

    def run_full_test(self, config_service, options):
        """Run full API tests for all integrations."""
        self.stdout.write(self.style.SUCCESS("Running full API integration tests..."))

        results = config_service.check_all_apis()

        if options["json"]:
            self.stdout.write(json.dumps(results, indent=2))
        else:
            self.display_full_results(results)

    def display_quick_results(self, results):
        """Display quick check results in human-readable format."""
        self.stdout.write("\n=== API Configuration Status ===\n")

        for api_name, config in results.items():
            status = "✓" if config["configured"] else "✗"
            self.stdout.write(f"{status} {api_name.upper()}:")

            if api_name == "openai":
                if config["configured"]:
                    self.stdout.write(
                        f'  API Key: {config["api_key_length"]} characters'
                    )
                else:
                    self.stdout.write(f"  API Key: Not configured")

            elif api_name == "adzuna":
                if config["configured"]:
                    self.stdout.write(f'  App ID: {config["app_id_length"]} characters')
                    self.stdout.write(
                        f'  API Key: {config["api_key_length"]} characters'
                    )
                else:
                    self.stdout.write(f"  Credentials: Not configured")

            elif api_name == "skyvern":
                if config["configured"]:
                    self.stdout.write(
                        f'  API Key: {config["api_key_length"]} characters'
                    )
                    self.stdout.write(f'  Base URL: {config["base_url"]}')
                else:
                    self.stdout.write(f"  API Key: Not configured")

            self.stdout.write("")

    def display_api_result(self, api_name, result):
        """Display single API test result."""
        if result["status"] == "success":
            self.stdout.write(
                self.style.SUCCESS(f'✓ {api_name.upper()}: {result["message"]}')
            )

            # Display additional info if available
            if "model" in result:
                self.stdout.write(f'  Model: {result["model"]}')
            if "embedding_dimension" in result:
                self.stdout.write(
                    f'  Embedding dimension: {result["embedding_dimension"]}'
                )
            if "total_jobs_available" in result:
                self.stdout.write(f'  Jobs available: {result["total_jobs_available"]}')
        else:
            self.stdout.write(
                self.style.ERROR(f'✗ {api_name.upper()}: {result["message"]}')
            )

    def display_full_results(self, results):
        """Display full test results in human-readable format."""
        self.stdout.write("\n=== API Integration Test Results ===\n")

        for api_name in ["openai", "adzuna", "skyvern"]:
            if api_name in results:
                self.display_api_result(api_name, results[api_name])

        # Display summary
        if "summary" in results:
            summary = results["summary"]
            self.stdout.write(f"\n=== Summary ===")
            self.stdout.write(f'Total APIs: {summary["total"]}')
            self.stdout.write(f'Configured: {summary["configured"]}')
            self.stdout.write(f'Working: {summary["working"]}')
            self.stdout.write(f'Failed: {summary["failed"]}')

            if summary["working"] == summary["total"]:
                self.stdout.write(
                    self.style.SUCCESS("\n🎉 All APIs are working correctly!")
                )
            elif summary["configured"] == 0:
                self.stdout.write(
                    self.style.WARNING(
                        "\n⚠️  No APIs are configured. Please add API keys to your .env file."
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        "\n❌ Some APIs are not working. Check the errors above."
                    )
                )
