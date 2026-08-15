from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from campaigns.models import Campaign
from scheduling.idempotency import make_idempotency_key
from scheduling.models import ScheduledPost


class Command(BaseCommand):
    help = (
        "Simulates a worker that claimed a ScheduledPost row and then "
        "crashed before finishing -- for live-demoing the stale-claim "
        "reclaim mechanism without needing to time a real Ctrl+C."
    )

    def handle(self, *args, **options):
        campaign = Campaign.objects.order_by("-created_at").first()
        if not campaign:
            self.stdout.write(self.style.ERROR("No campaigns exist yet -- run seed_demo first."))
            return

        scheduled_post, _ = ScheduledPost.objects.get_or_create(
            campaign=campaign,
            platform="x",
            defaults={
                "scheduled_at": timezone.now() - timedelta(minutes=10),
                "idempotency_key": make_idempotency_key(campaign.id, "x"),
            },
        )
        scheduled_post.status = "claimed"
        scheduled_post.claimed_at = timezone.now() - timedelta(minutes=5)  # stale
        scheduled_post.claimed_by = "worker-that-crashed-SIMULATED"
        scheduled_post.platform_post_id = None
        scheduled_post.published_at = None
        scheduled_post.save()

        self.stdout.write(
            self.style.WARNING(
                f"Simulated a crashed worker: ScheduledPost {scheduled_post.id} "
                f"(campaign {campaign.id}, platform=x) is now status='claimed', "
                f"claimed_at=5 min ago. Watch the beat/worker logs -- the next "
                f"poll cycle (within 15s) should reclaim and republish it."
            )
        )