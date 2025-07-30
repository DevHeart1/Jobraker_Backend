import logging
from typing import Any, Dict, List, Optional

# from django.contrib.auth import get_user_model # User = get_user_model()
from apps.accounts.models import \
    UserProfile  # Assuming UserProfile is in accounts.models
from apps.common.services import VectorDBService  # For vector search
from apps.jobs.models import Job

# from apps.integrations.services.openai_service import EmbeddingService # If on-the-fly embedding is needed

logger = logging.getLogger(__name__)


class JobMatchService:
    """
    Service for matching users to jobs and vice-versa using embeddings and other criteria.
    """

    def __init__(self):
        self.vector_db_service = VectorDBService()
        # from apps.integrations.services.openai_service import EmbeddingService # For on-demand
        # self.embedding_service = EmbeddingService()

    def _calculate_cosine_similarity(
        self, vec_a: List[float], vec_b: List[float]
    ) -> Optional[float]:
        """
        Calculates cosine similarity between two vectors (lists of floats).
        Assumes vectors are already normalized (magnitude of 1).
        If not normalized, a full cosine similarity calculation (dot / (normA * normB)) is needed.
        OpenAI embeddings are typically normalized.
        """
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            logger.warning("Cosine similarity: Invalid or mismatched vectors.")
            return None

        # For normalized vectors, cosine similarity is just the dot product.
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))

        # Clamp the value to [-1, 1] due to potential floating point inaccuracies
        similarity = max(-1.0, min(1.0, dot_product))
        return similarity

    def find_matching_jobs_for_user(
        self,
        user_profile_id: Any,  # Can be UUID or int depending on UserProfile PK
        top_n: int = 10,
        user_profile_embedding_override: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Finds relevant job listings for a user based on their profile embedding.

        Args:
            user_profile_id: The ID of the UserProfile.
            top_n: The maximum number of matching jobs to return.
            user_profile_embedding_override: Optionally provide an embedding directly,
                                             bypassing fetching it from the UserProfile.

        Returns:
            A list of dictionaries, each representing a matched job, including
            the Job object (or its serialization) and the similarity_score.
            Example: [{'job': <Job object>, 'score': 0.85}, ...]
        """
        profile_embedding: Optional[List[float]] = None

        if user_profile_embedding_override:
            profile_embedding = user_profile_embedding_override
            logger.info(
                f"Using provided embedding override for matching jobs for user_profile_id: {user_profile_id}"
            )
        else:
            try:
                user_profile = UserProfile.objects.get(id=user_profile_id)
                # Decide which embedding to use from UserProfile.
                # profile_embedding = user_profile.profile_embedding
                # Or skills_embedding, or a weighted average if multiple are relevant.
                # For now, let's assume 'profile_embedding' is the primary one for general matching.
                if (
                    hasattr(user_profile, "profile_embedding")
                    and user_profile.profile_embedding
                ):
                    profile_embedding = user_profile.profile_embedding
                elif (
                    hasattr(user_profile, "skills_embedding")
                    and user_profile.skills_embedding
                ):  # Fallback
                    profile_embedding = user_profile.skills_embedding
                    logger.info(
                        f"Using skills_embedding as fallback for UserProfile {user_profile_id}"
                    )

                if not profile_embedding:
                    logger.warning(
                        f"UserProfile {user_profile_id} has no suitable embedding for job matching."
                    )
                    return []
                logger.info(
                    f"Retrieved profile embedding for UserProfile {user_profile_id}"
                )

            except UserProfile.DoesNotExist:
                logger.error(f"UserProfile with id {user_profile_id} not found.")
                return []
            except Exception as e:
                logger.error(
                    f"Error fetching UserProfile or its embedding for id {user_profile_id}: {e}"
                )
                return []

        if not profile_embedding:  # Should be caught above, but as a safeguard
            logger.error(
                f"No profile embedding available for UserProfile {user_profile_id} for job matching."
            )
            return []

        # Search for similar job listings in the vector database
        # The VectorDocument for jobs stores 'combined_embedding' of job title+description
        try:
            filter_criteria = {"source_type": "job_listing"}
            # Could add more filters, e.g., based on user_profile.job_preferences if that model exists
            # such as location, job_type, experience_level, if these are stored in VectorDocument metadata.
            # For example: if user_profile.preferred_location:
            #    filter_criteria['metadata__location__icontains'] = user_profile.preferred_location

            logger.info(
                f"Searching VectorDB for matching jobs for user {user_profile_id} with top_n={top_n}"
            )
            similar_job_documents = self.vector_db_service.search_similar_documents(
                query_embedding=profile_embedding,
                top_n=top_n,
                filter_criteria=filter_criteria,
            )
        except Exception as e:
            logger.error(
                f"Error searching similar job documents in VectorDBService for user {user_profile_id}: {e}"
            )
            return []

        matched_jobs_output = []
        if not similar_job_documents:
            logger.info(
                f"No similar job documents found in VectorDB for user {user_profile_id}."
            )
            return []

        # Retrieve full Job objects based on source_id from VectorDocument results
        job_ids_to_fetch = [
            doc.get("source_id")
            for doc in similar_job_documents
            if doc.get("source_id")
        ]

        if not job_ids_to_fetch:
            logger.warning(
                f"VectorDB returned documents but no source_ids for user {user_profile_id}."
            )
            return []

        # Fetch Job objects in bulk
        # We need a way to map scores back to these jobs.
        # Create a map of source_id -> similarity_score from similar_job_documents
        score_map = {
            doc.get("source_id"): doc.get("similarity_score", 0.0)
            for doc in similar_job_documents
            if doc.get("source_id")
        }

        try:
            # Fetch active jobs only
            jobs = Job.objects.filter(id__in=job_ids_to_fetch, status="active")

            for job in jobs:
                job_id_str = str(job.id)
                if job_id_str in score_map:
                    matched_jobs_output.append(
                        {
                            "job": job,  # The Job model instance
                            "score": score_map[job_id_str],
                        }
                    )

            # Sort by score descending, as search_similar_documents already orders by similarity (distance)
            # but if we fetch Job objects separately, we might want to re-apply or ensure order.
            # The VectorDB search already returns them ordered by similarity.
            # If the order from job_ids_to_fetch and then jobs query is preserved, this sort might be redundant
            # but it's safer to ensure.
            matched_jobs_output.sort(key=lambda x: x["score"], reverse=True)

            logger.info(
                f"Successfully matched {len(matched_jobs_output)} jobs for user {user_profile_id}."
            )

        except Exception as e:
            logger.error(f"Error fetching full Job objects for matching: {e}")
            return []  # Or return partially processed if some jobs were fetched

        return matched_jobs_output

    # score_job_for_user method will be implemented in the next step of the plan
    def score_job_for_user(
        self,
        user_profile_id: Any,
        job_id: Any,
        user_profile_embedding_override: Optional[List[float]] = None,
        job_embedding_override: Optional[List[float]] = None,
    ) -> Optional[float]:
        """
        Calculates a direct similarity score (e.g., cosine similarity) between
        a user profile and a specific job using their stored embeddings.

        Args:
            user_profile_id: ID of the UserProfile.
            job_id: ID of the Job.
            user_profile_embedding_override: Optionally provide user embedding directly.
            job_embedding_override: Optionally provide job embedding directly.

        Returns:
            The similarity score (float between 0.0 and 1.0, assuming normalized embeddings
            and dot product resulting in positive correlation), or None if embeddings
            are missing or an error occurs. Higher score means more similar.
        """
        user_embedding: Optional[List[float]] = None
        job_embedding_val: Optional[List[float]] = (
            None  # Renamed to avoid conflict with Job model field
        )

        # Get User Profile Embedding
        if user_profile_embedding_override:
            user_embedding = user_profile_embedding_override
        else:
            try:
                user_profile = UserProfile.objects.get(id=user_profile_id)
                # Prioritize 'profile_embedding', fallback to 'skills_embedding'
                if (
                    hasattr(user_profile, "profile_embedding")
                    and user_profile.profile_embedding
                ):
                    user_embedding = user_profile.profile_embedding
                elif (
                    hasattr(user_profile, "skills_embedding")
                    and user_profile.skills_embedding
                ):
                    user_embedding = user_profile.skills_embedding

                if not user_embedding:
                    logger.warning(
                        f"UserProfile {user_profile_id} has no suitable embedding for direct scoring."
                    )
            except UserProfile.DoesNotExist:
                logger.error(f"UserProfile {user_profile_id} not found for scoring.")
                return None
            except Exception as e:
                logger.error(
                    f"Error fetching UserProfile {user_profile_id} embedding: {e}"
                )
                return None

        # Get Job Embedding
        if job_embedding_override:
            job_embedding_val = job_embedding_override
        else:
            try:
                job = Job.objects.get(id=job_id)
                # Assuming 'combined_embedding' is the primary one for job matching
                if hasattr(job, "combined_embedding") and job.combined_embedding:
                    job_embedding_val = job.combined_embedding
                elif (
                    hasattr(job, "job_embedding") and job.job_embedding
                ):  # Fallback if 'job_embedding' is the old field
                    job_embedding_val = job.job_embedding

                if not job_embedding_val:
                    logger.warning(
                        f"Job {job_id} has no suitable embedding for direct scoring."
                    )
            except Job.DoesNotExist:
                logger.error(f"Job {job_id} not found for scoring.")
                return None
            except Exception as e:
                logger.error(f"Error fetching Job {job_id} embedding: {e}")
                return None

        if not user_embedding or not job_embedding_val:
            logger.warning(
                f"Missing one or both embeddings for scoring: UserProf {user_profile_id}, Job {job_id}."
            )
            return None

        similarity_score = self._calculate_cosine_similarity(
            user_embedding, job_embedding_val
        )

        if similarity_score is None:
            logger.warning(
                f"Could not calculate similarity for UserProf {user_profile_id}, Job {job_id}."
            )
            return None

        # Cosine similarity for normalized vectors (via dot product) ranges from -1 to 1.
        # If we want a score from 0 to 1 (where 1 is most similar):
        # score_0_to_1 = (similarity_score + 1) / 2
        # However, OpenAI embeddings are designed such that higher dot product (closer to 1) is more similar.
        # Negative values mean dissimilar. Values near 0 mean unrelated.
        # For job matching, we are typically interested in positive correlation.
        # Let's return the raw cosine similarity for now, or a scaled version if required by consumers.
        # The prompt for this method says "float between 0.0 and 1.0", so we scale.

        scaled_score = (similarity_score + 1) / 2
        logger.info(
            f"Calculated similarity score for UserProf {user_profile_id} and Job {job_id}: {scaled_score:.4f} (raw cosine: {similarity_score:.4f})"
        )
        return round(scaled_score, 4)

    def find_similar_jobs(self, job_id: Any, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Finds relevant job listings similar to a given job based on its embedding.

        Args:
            job_id: The ID of the Job to find similarities for.
            top_n: The maximum number of matching jobs to return.

        Returns:
            A list of dictionaries, each representing a matched job, including
            the Job object and the similarity_score.
        """
        try:
            job = Job.objects.get(id=job_id)
            if not hasattr(job, "combined_embedding") or not job.combined_embedding:
                logger.warning(f"Job {job_id} has no embedding for similarity search.")
                return []
            job_embedding = job.combined_embedding
        except Job.DoesNotExist:
            logger.error(f"Job with id {job_id} not found for similarity search.")
            return []

        try:
            filter_criteria = {"source_type": "job_listing"}

            similar_job_documents = self.vector_db_service.search_similar_documents(
                query_embedding=job_embedding,
                top_n=top_n + 1,  # Fetch one extra to exclude the job itself
                filter_criteria=filter_criteria,
            )
        except Exception as e:
            logger.error(
                f"Error searching similar job documents in VectorDBService for job {job_id}: {e}"
            )
            return []

        matched_jobs_output = []
        if not similar_job_documents:
            return []

        job_ids_to_fetch = [
            doc.get("source_id")
            for doc in similar_job_documents
            if doc.get("source_id") and str(doc.get("source_id")) != str(job_id)
        ]

        if not job_ids_to_fetch:
            return []

        score_map = {
            doc.get("source_id"): doc.get("similarity_score", 0.0)
            for doc in similar_job_documents
        }

        try:
            jobs = Job.objects.filter(id__in=job_ids_to_fetch, status="active")

            for j in jobs:
                job_id_str = str(j.id)
                if job_id_str in score_map:
                    matched_jobs_output.append(
                        {"job": j, "score": score_map[job_id_str]}
                    )

            matched_jobs_output.sort(key=lambda x: x["score"], reverse=True)
            logger.info(
                f"Successfully matched {len(matched_jobs_output)} similar jobs for job {job_id}."
            )

        except Exception as e:
            logger.error(
                f"Error fetching full Job objects for similarity matching: {e}"
            )
            return []

        return matched_jobs_output[:top_n]

    def generate_recommendations_for_user(
        self,
        user_profile_id: Any,
        num_recommendations: int = 10,
        algorithm_version: str = "v1.0_profile_match",
    ) -> List[Dict[str, Any]]:
        """
        Generates and stores job recommendations for a user.
        It uses find_matching_jobs_for_user, then filters out already applied/dismissed jobs,
        and saves new/updated recommendations.

        Args:
            user_profile_id: The ID of the UserProfile.
            num_recommendations: The desired number of recommendations to generate/store.
            algorithm_version: A version string for the recommendation algorithm used.

        Returns:
            A list of dictionaries representing the created/updated RecommendedJob entries.
            Example: [{'recommended_job_id': rec.id, 'job_id': job.id, ...}, ...]
        """
        from django.contrib.auth import get_user_model

        from apps.jobs.models import (  # Import here to avoid circularity at module level
            Application, RecommendedJob)

        User = get_user_model()

        try:
            # Assuming UserProfile ID is the same as User ID for simplicity in this example,
            # or that UserProfile has a 'user_id' field or is directly the user's profile.
            # If user_profile_id is for UserProfile model, and UserProfile has a OneToOne with User:
            user = User.objects.get(profile__id=user_profile_id)
        except User.DoesNotExist:
            logger.error(
                f"User for UserProfile ID {user_profile_id} not found for generating recommendations."
            )
            return []
        except (
            Exception
        ) as e:  # Catch other potential errors like User.profile.RelatedObjectDoesNotExist
            logger.error(
                f"Error fetching user for UserProfile ID {user_profile_id}: {e}"
            )
            return []

        # 1. Get potential job matches using existing service method
        # Fetch more than num_recommendations initially to account for filtering.
        potential_matches = self.find_matching_jobs_for_user(
            user_profile_id=user_profile_id,
            top_n=num_recommendations * 3,  # Fetch more (e.g., 3x) to filter from
        )

        if not potential_matches:
            logger.info(
                f"No initial matches from find_matching_jobs_for_user for UserProfile {user_profile_id}."
            )
            return []

        # 2. Filter out jobs already applied to by the user
        applied_job_ids = set(
            Application.objects.filter(user=user).values_list("job_id", flat=True)
        )

        # 3. Filter out jobs already dismissed or marked irrelevant by the user
        existing_recommendations = RecommendedJob.objects.filter(user=user)
        dismissed_job_ids = set(
            existing_recommendations.filter(
                status__in=["dismissed", "irrelevant"]
            ).values_list("job_id", flat=True)
        )

        final_recommendations_data = []
        processed_job_ids_for_this_batch = (
            set()
        )  # To avoid duplicates if find_matching_jobs had them (unlikely with current logic)

        for match in potential_matches:
            job = match["job"]
            score = match["score"]

            if job.id in applied_job_ids:
                logger.debug(
                    f"Skipping job {job.id} for recs (already applied) for user {user.id}"
                )
                continue
            if job.id in dismissed_job_ids:
                logger.debug(
                    f"Skipping job {job.id} for recs (dismissed/irrelevant) for user {user.id}"
                )
                continue
            if job.id in processed_job_ids_for_this_batch:
                continue

            # Create or Update RecommendedJob entry
            recommended_job, created = RecommendedJob.objects.update_or_create(
                user=user,
                job=job,
                defaults={
                    "score": score,
                    "algorithm_version": algorithm_version,
                    "status": "pending_review",  # Reset to pending review if re-recommended or new
                    # 'recommended_at' will be updated by auto_now on save if it's an update,
                    # or set by auto_now_add if created.
                },
            )

            action_status = "created" if created else "updated"
            logger.info(
                f"Recommendation {action_status} for user {user.id}, job {job.id} (RecID: {recommended_job.id}) with score {score:.3f}"
            )

            final_recommendations_data.append(
                {
                    "recommended_job_id": recommended_job.id,
                    "job_id": job.id,
                    "job_title": job.title,
                    "score": score,
                    "status": recommended_job.status,  # The status after update_or_create
                    "action": action_status,
                }
            )
            processed_job_ids_for_this_batch.add(job.id)

            if len(final_recommendations_data) >= num_recommendations:
                break

        logger.info(
            f"Generated {len(final_recommendations_data)} final recommendations for user {user.id} (profile_id {user_profile_id})."
        )
        return final_recommendations_data
