from django.core.management.base import BaseCommand
from django_elasticsearch_dsl.management.commands.search_index import \
    Command as DslBaseCommand
from django_elasticsearch_dsl.registries import registry


class Command(DslBaseCommand):
    help = "Manages Elasticsearch Jobraker indices (create, rebuild, delete, update)"

    # Overriding the handle method or adding specific options might not be necessary
    # if the base command's functionality is sufficient.
    # The base command already provides --create, --populate, --rebuild, --delete, --update options.

    # For Jobraker, we might want to add a specific option to target only our job index,
    # or provide a simpler interface if the default is too verbose.
    # However, for now, inheriting directly gives us all the power of the original command.

    # Example of how you might customize:
    # def add_arguments(self, parser):
    #     super().add_arguments(parser)
    #     parser.add_argument(
    #         '--rebuild-jobs',
    #         action='store_true',
    #         help='Specifically rebuild the jobraker-jobs index.'
    #     )

    # def handle(self, *args, **options):
    #     if options['rebuild_jobs']:
    #         # Logic to specifically target and rebuild the job index
    #         # This would involve finding the 'jobraker-jobs' index or documents associated with it.
    #         # For example:
    #         from apps.jobs.documents import JOB_INDEX_NAME # Assuming JOB_INDEX_NAME is defined
    #         self.stdout.write(f"Rebuilding specific index: {JOB_INDEX_NAME}")

    #         # You might call specific parts of the parent command's logic here,
    #         # or implement your own sequence of delete, create, populate.
    #         # This can get complex if you're trying to replicate parent command logic.

    #         # For simplicity, if you just want to run the default command but perhaps with
    #         # some pre-checks or logging, you'd call super().handle().
    #         # If you want to ensure only specific indices are affected, it's often easier
    #         # to rely on the --models or --index options of the base command.

    #         # Example: Rebuild only the JobDocument's index
    #         # This is pseudo-code for concept, actual implementation would use dsl utilities
    #         # self._delete(indices=[JOB_INDEX_NAME])
    #         # self._create(indices=[JOB_INDEX_NAME])
    #         # self._populate(models=['jobs.Job']) # or using the document class
    #         self.stdout.write(self.style.SUCCESS(f"Successfully rebuilt index: {JOB_INDEX_NAME}"))
    #         return

    #     super().handle(*args, **options)

    # For now, a simple inheritance is sufficient to make the command available.
    # Users can then run:
    # python manage.py search_index --rebuild (processes all registered documents)
    # python manage.py search_index --rebuild --models jobs (processes only models in 'jobs' app)
    # python manage.py search_index --rebuild --index jobraker-jobs (processes only this index)
    # The base command from django-elasticsearch-dsl is quite powerful.
    pass
