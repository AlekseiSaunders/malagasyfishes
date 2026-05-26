"""Initial migration for the curated-submission queue.

Creates ``PopulationSubmission`` (Gate 15) and ``HusbandryContribution``
(Gate 10 reopened) tables in a single migration. Architecture D8: both
models live in the new ``submissions`` app from day one to avoid the
"move HusbandryContribution from husbandry → submissions later" pain.

The abstract ``Submission`` base does NOT generate a parent table; both
concrete subclasses get their own complete schema. The shared fields
(submitter_user, status, reviewer, etc.) appear on both tables
identically by design.
"""

from __future__ import annotations

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("populations", "0007_exsitupopulation_last_edited_at_and_more"),
        ("species", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PopulationSubmission",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("in_review", "In review"),
                            ("accepted", "Accepted"),
                            ("rejected", "Rejected"),
                            ("spam", "Spam"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=20,
                    ),
                ),
                (
                    "review_notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text=(
                            "Free-text reason captured by the reviewer. On rejection, this is "
                            "shown to the submitter in the rejection email."
                        ),
                    ),
                ),
                (
                    "submitter_ip",
                    models.GenericIPAddressField(blank=True, null=True),
                ),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "count_total",
                    models.PositiveIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(10000),
                        ],
                    ),
                ),
                (
                    "count_male",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[
                            django.core.validators.MaxValueValidator(10000)
                        ],
                    ),
                ),
                (
                    "count_female",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[
                            django.core.validators.MaxValueValidator(10000)
                        ],
                    ),
                ),
                (
                    "count_unsexed",
                    models.PositiveIntegerField(
                        default=0,
                        validators=[
                            django.core.validators.MaxValueValidator(10000)
                        ],
                    ),
                ),
                (
                    "breeding_status",
                    models.CharField(
                        choices=[
                            ("breeding", "Breeding"),
                            ("non-breeding", "Not breeding"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=20,
                    ),
                ),
                ("last_census_date", models.DateField(
                    help_text="When the submitter last counted these fish.",
                )),
                ("notes", models.TextField(blank=True, max_length=1000)),
                (
                    "accepted_population",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="source_submission",
                        to="populations.exsitupopulation",
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_population_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "species",
                    models.ForeignKey(
                        help_text=(
                            "FK to existing species; no 'other' path (Gate 15 Q2 lock)."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="population_submissions",
                        to="species.species",
                    ),
                ),
                (
                    "submitter_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="population_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "submissions_populationsubmission",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="HusbandryContribution",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("in_review", "In review"),
                            ("accepted", "Accepted"),
                            ("rejected", "Rejected"),
                            ("spam", "Spam"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=20,
                    ),
                ),
                (
                    "review_notes",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text=(
                            "Free-text reason captured by the reviewer. On rejection, this is "
                            "shown to the submitter in the rejection email."
                        ),
                    ),
                ),
                (
                    "submitter_ip",
                    models.GenericIPAddressField(blank=True, null=True),
                ),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "message",
                    models.TextField(help_text="The husbandry tip body. Free-form."),
                ),
                (
                    "citations",
                    models.TextField(
                        blank=True,
                        help_text="Optional sources / URLs / references.",
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_husbandry_contributions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "species",
                    models.ForeignKey(
                        help_text=(
                            "FK to existing species; nullable to allow "
                            "'species not listed' path (Gate 10 spec)."
                        ),
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="husbandry_contributions",
                        to="species.species",
                    ),
                ),
                (
                    "submitter_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="husbandry_contributions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "submissions_husbandrycontribution",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="populationsubmission",
            index=models.Index(
                fields=["status", "-created_at"],
                name="submissions_status_d2bc66_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="populationsubmission",
            index=models.Index(
                fields=["submitter_user", "status"],
                name="submissions_submitt_8f1f3d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="husbandrycontribution",
            index=models.Index(
                fields=["status", "-created_at"],
                name="submissions_status_8a7c22_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="husbandrycontribution",
            index=models.Index(
                fields=["submitter_user", "status"],
                name="submissions_submitt_2a8f1b_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="husbandrycontribution",
            index=models.Index(
                fields=["species", "status"],
                name="submissions_species_5d3e44_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="populationsubmission",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        count_male=0,
                        count_female=0,
                        count_unsexed=0,
                    )
                    | models.Q(
                        count_total__gte=models.F("count_male")
                        + models.F("count_female")
                        + models.F("count_unsexed")
                    )
                ),
                name="population_submission_sex_sum_le_total",
            ),
        ),
    ]
