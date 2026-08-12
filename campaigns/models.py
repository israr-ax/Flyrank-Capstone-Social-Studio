import uuid
from django.db import models


class BlogPost(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=300)
    body = models.TextField()
    url = models.URLField()
    source_image = models.ImageField(upload_to="blog_sources/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Campaign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blog_post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name="campaigns")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Campaign({self.id}) for {self.blog_post.title}"

    @property
    def status(self) -> str:
        """
        Derived, not stored. Cross-app lookup via the related_name on
        ScheduledPost ("scheduled_posts") rather than importing the
        scheduling app's model directly, to avoid a circular import
        between campaigns <-> scheduling.
        """
        statuses = list(self.scheduled_posts.values_list("status", flat=True))
        if not statuses:
            return "queued"
        if all(s == "published" for s in statuses):
            return "published"
        if any(s == "failed" for s in statuses) and all(s in ("failed", "published") for s in statuses):
            return "failed"
        if any(s in ("claimed", "publishing") for s in statuses):
            return "publishing"
        return "queued"