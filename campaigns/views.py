from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Campaign
from .serializers import CampaignCreateSerializer, CampaignDetailSerializer


class CampaignListCreateView(APIView):
    def get(self, request):
        campaigns = Campaign.objects.all().order_by("-created_at")
        serializer = CampaignDetailSerializer(campaigns, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # -> 400 on bad input, never a 500
        campaign = serializer.save()
        return Response(CampaignDetailSerializer(campaign).data, status=status.HTTP_201_CREATED)


class CampaignDetailView(APIView):
    def get(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(CampaignDetailSerializer(campaign).data)


def health(request):
    return JsonResponse({"status": "ok"})