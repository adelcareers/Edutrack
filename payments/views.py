from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.conf import settings
from accounts.decorators import role_required


def pricing_page_view(request):
    """View to display subscription plans."""
    plans = [
        {
            'name': 'Essential',
            'price': 'Free',
            'interval': 'forever',
            'description': 'Get started with home education tracking.',
            'storage': '20 GB',
            'features': [
                'Full access to all features',
                'Store lessons and assignments',
                'Track student progress',
                'Generate reports',
                'Upload evidence files',
                'Schedule lessons',
                'Parent-student collaboration',
            ],
            'button_text': 'Get Started',
            'button_class': 'btn-outline-primary',
            'button_link': '#',
            'is_pro': False
        },
        {
            'name': 'Premium',
            'price': '£6',
            'interval': '/ month',
            'description': 'Unlimited storage for growing families.',
            'storage': '200 GB',
            'features': [
                'Full access to all features',
                'Store lessons and assignments',
                'Track student progress',
                'Generate reports',
                'Upload evidence files',
                'Schedule lessons',
                'Parent-student collaboration',
            ],
            'button_text': 'Upgrade to Premium',
            'button_class': 'btn-primary',
            'button_link': '/payments/checkout/',
            'is_pro': True
        }
    ]
    return render(request, 'payments/pricing.html', {'plans': plans})


@login_required
@role_required('parent')
def checkout_view(request):
    """View to display Stripe checkout or test mode banner.

    Shows either Stripe form or test mode banner based on STRIPE_ENABLED.
    """
    context = {
        'stripe_enabled': settings.STRIPE_ENABLED,
        'stripe_key': settings.STRIPE_PUBLISHABLE_KEY,
    }
    return render(request, 'payments/checkout.html', context)


@login_required
@role_required('parent')
def success_view(request):
    """View to display success message after payment.

    Automatically activates premium subscription for testing purposes.
    """
    profile = request.user.profile
    if profile.subscription_tier != 'premium':
        profile.subscription_tier = 'premium'
        profile.storage_limit_gb = 200
        profile.subscription_active = True
        profile.save()

    return render(request, 'payments/success.html')
