from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
import random

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_random_tip(request):
    """Fetch a random chess tip from the database."""
    from ..models import ChessTip
    tips = list(ChessTip.objects.all())
    if not tips:
        return Response({
            "text": "The game of chess is not merely an idle amusement; several very valuable qualities of the mind are to be acquired and strengthened by it. - Benjamin Franklin",
            "category": "Classic"
        })
    
    tip = random.choice(tips)
    return Response({
        "text": tip.text,
        "category": tip.category or "General"
    })