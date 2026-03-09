from django.test import TestCase
from django.urls import reverse

class PricingPageTests(TestCase):
    def test_pricing_page_status_code(self):
        url = reverse('payments:pricing')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_pricing_page_content(self):
        url = reverse('payments:pricing')
        response = self.client.get(url)
        self.assertContains(response, 'Free Tier')
        self.assertContains(response, 'Pro Tier')
        self.assertContains(response, 'Choose Pro')
        self.assertContains(response, '/payments/checkout/')

