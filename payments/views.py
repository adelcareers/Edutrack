from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from accounts.decorators import role_required

def pricing_page_view(request):
    """View to display subscription plans."""
    plans = [
        {
            'name': 'Free Tier',
            'price': '£0',
            'interval': 'forever',
            'description': 'Basic tools to get started.',
            'features': [
                'Add up to 2 children',
                'Basic tracker logging',
                'Generate simple text reports',
            ],
            'button_text': 'Current Plan',
            'button_class': 'btn-outline-primary',
            'button_link': '#',
            'is_pro': False
        },
        {
            'name': 'Pro Tier',
            'price': '£6',
            'interval': '/ month',
            'description': 'Everything you need for full home education tracking.',
            'features': [
                'Unlimited children',
                'Advanced tracker logging with evidence',
                'Generate LA-ready PDF reports',
                'Share reports securely via links',
                'Schedule generation'
            ],
            'button_text': 'Choose Pro',
            'button_class': 'btn-primary',
            'button_link': '/payments/checkout/', # We'll wire this up later
            'is_pro': True
        }
    ]
    return render(request, 'payments/pricing.html', {'plans': plans})


@login_required
@role_required('parent')
def checkout_view(request):
    """View to display Stripe checkout or test mode banner based on feature flag."""
    context = {
        'stripe_enabled': settings.STRIPE_ENABLED,
        'stripe_key': settings.STRIPE_PUBLISHABLE_KEY,
    }
    return render(request, 'payments/checkout.html', context)
