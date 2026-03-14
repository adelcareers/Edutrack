from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from accounts.models import UserProfile


class PricingPageTests(TestCase):
    def test_pricing_page_status_code(self):
        url = reverse('payments:pricing')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_pricing_page_content(self):
        url = reverse('payments:pricing')
        response = self.client.get(url)
        self.assertContains(response, 'Essential')
        self.assertContains(response, 'Premium')
        self.assertContains(response, 'Upgrade to Premium')
        self.assertContains(response, '20 GB')
        self.assertContains(response, '200 GB')
        self.assertContains(response, '/payments/checkout/')


class CheckoutViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='parent', password='pw')
        UserProfile.objects.create(user=self.user, role='parent')

    @override_settings(STRIPE_ENABLED=False)
    def test_checkout_test_mode(self):
        self.client.login(username='parent', password='pw')
        response = self.client.get(reverse('payments:checkout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Mode')
        self.assertContains(response, 'Simulate Payment Success')

    @override_settings(STRIPE_ENABLED=True)
    def test_checkout_stripe_enabled(self):
        self.client.login(username='parent', password='pw')
        response = self.client.get(reverse('payments:checkout'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stripe Checkout Form Stub')

class SuccessViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='parent', password='pw')
        UserProfile.objects.create(
            user=self.user, role='parent', subscription_active=False
        )

    def test_success_view_activates_subscription(self):
        self.client.login(username='parent', password='pw')
        response = self.client.get(reverse('payments:success'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Payment Successful!')

        # Verify profile was upgraded to premium
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.subscription_tier, 'premium')
        self.assertEqual(self.user.profile.storage_limit_gb, 200)
        self.assertTrue(self.user.profile.subscription_active)


