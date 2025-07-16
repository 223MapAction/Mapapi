from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from Mapapi.models import Incident, Zone, Evenement, Contact, Communaute, Category
from Mapapi.serializer import (
    IncidentSerializer, ZoneSerializer, EvenementSerializer,
    ContactSerializer, CommunauteSerializer, UserSerializer, CategorySerializer, EluToZoneSerializer
)

User = get_user_model()

class IncidentSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@example.com', password='password')
        self.zone = Zone.objects.create(name='Test Zone')
        self.category = Category.objects.create(name='Test Category')
        self.incident_data = {
            'title': 'Test Incident',
            'description': 'Test Description',
            'zone': 'Test Zone',
            'user_id': self.user,  # Use the User instance directly
            'etat': 'declared',
            'category_id': self.category,
            'lattitude': '40.7128',
            'longitude': '-74.0060',
        }
        self.incident = Incident.objects.create(**self.incident_data)
        self.serializer = IncidentSerializer(instance=self.incident)

    def test_contains_expected_fields(self):
        data = self.serializer.data
        self.assertCountEqual(data.keys(), ['id', 'title', 'description', 'zone', 'user_id', 'etat', 'category_id', 'lattitude', 'longitude', 'photo', 'video', 'audio', 'indicateur_id', 'slug', 'category_ids', 'created_at', 'taken_by'])

    def test_title_field_content(self):
        data = self.serializer.data
        self.assertEqual(data['title'], self.incident_data['title'])

    def test_create_incident(self):
        new_incident_data = {
            'title': 'New Incident',
            'description': 'New Description',
            'zone': self.zone.id,
            'user_id': self.user.id,
            'etat': 'resolved'
        }
        serializer = IncidentSerializer(data=new_incident_data)
        self.assertTrue(serializer.is_valid())
        new_incident = serializer.save()
        self.assertEqual(new_incident.title, 'New Incident')
        self.assertEqual(new_incident.etat, 'resolved')

class ZoneSerializerTest(TestCase):
    def setUp(self):
        self.zone_data = {
            'name': 'Test Zone',
            'description': 'Test Description',
            'lattitude': '12.345',
            'longitude': '67.890'
        }
        self.zone = Zone.objects.create(**self.zone_data)
        self.serializer = ZoneSerializer(instance=self.zone)

    def test_contains_expected_fields(self):
        data = self.serializer.data
        self.assertCountEqual(data.keys(), ['id', 'name', 'description', 'lattitude', 'longitude', 'photo', 'created_at'])

    def test_name_field_content(self):
        data = self.serializer.data
        self.assertEqual(data['name'], self.zone_data['name'])

class EvenementSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='test@example.com', password='password')
        self.event_data = {
            'title': 'Test Event',
            'description': 'Test Description',
            'date': timezone.make_aware(timezone.datetime(2023, 5, 1)),
            'user_id': self.user,
            'zone': 'Test Zone',
            'lieu': 'Test Location',
        }
        self.event = Evenement.objects.create(**self.event_data)
        self.serializer = EvenementSerializer(instance=self.event)

    def test_contains_expected_fields(self):
        data = self.serializer.data
        self.assertCountEqual(data.keys(), ['id', 'title', 'description', 'date', 'user_id', 'zone', 'photo', 'lieu', 'video', 'audio', 'latitude', 'longitude', 'created_at'])

    def test_title_field_content(self):
        data = self.serializer.data
        self.assertEqual(data['title'], self.event_data['title'])

class ContactSerializerTest(TestCase):
    def setUp(self):
        self.contact_data = {
            'objet': 'Test Contact',
            'email': 'test@example.com',
            'message': 'Test Message'
        }
        self.contact = Contact.objects.create(**self.contact_data)
        self.serializer = ContactSerializer(instance=self.contact)

    def test_contains_expected_fields(self):
        data = self.serializer.data
        self.assertCountEqual(data.keys(), ['id', 'objet', 'email', 'message', 'created_at'])

    def test_email_field_content(self):
        data = self.serializer.data
        self.assertEqual(data['email'], self.contact_data['email'])

class CommunauteSerializerTest(TestCase):
    def setUp(self):
        self.zone = Zone.objects.create(name='Test Zone')
        self.community_data = {
            'name': 'Test Community',
            'zone': self.zone,
        }
        self.community = Communaute.objects.create(**self.community_data)
        self.serializer = CommunauteSerializer(instance=self.community)

    def test_contains_expected_fields(self):
        data = self.serializer.data
        self.assertCountEqual(data.keys(), ['id', 'name', 'zone', 'created_at'])

    def test_name_field_content(self):
        data = self.serializer.data
        self.assertEqual(data['name'], self.community_data['name'])


class UserSerializerTestCase(TestCase):
    def test_user_serializer(self):
        user_data = {
            'email': 'test@example.com',
            'password': 'testpassword',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '1234567890',
            'user_type': 'citizen',
        }
        serializer = UserSerializer(data=user_data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()
        self.assertEqual(user.email, user_data['email'])
        self.assertEqual(user.first_name, user_data['first_name'])
        self.assertEqual(user.last_name, user_data['last_name'])
        self.assertEqual(user.phone, user_data['phone'])
        self.assertEqual(user.user_type, user_data['user_type'])
        self.assertTrue(user.check_password(user_data['password']))

class CategorySerializerTestCase(TestCase):
    def test_category_serializer(self):
        category_data = {
            'name': 'Test Category',
            'description': 'This is a test category',
        }
        serializer = CategorySerializer(data=category_data)
        self.assertTrue(serializer.is_valid())
        category = serializer.save()
        self.assertEqual(category.name, category_data['name'])
        self.assertEqual(category.description, category_data['description'])

class IncidentSerializerTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpassword',
            first_name='Test',
            last_name='User'
        )
        self.category = Category.objects.create(
            name='Test Category',
            description='Test Description'
        )

    def test_incident_serializer(self):
        incident_data = {
            'title': 'Test Incident',
            'description': 'This is a test incident',
            'user_id': self.user.id,
            'category_id': self.category.id,
            'lattitude': '40.7128',  # Corrected field name
            'longitude': '-74.0060',
            'zone': 'Test Zone',  # Added required field
        }
        serializer = IncidentSerializer(data=incident_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        incident = serializer.save()
        self.assertEqual(incident.title, incident_data['title'])
        self.assertEqual(incident.description, incident_data['description'])
        self.assertEqual(incident.user_id, self.user)
        self.assertEqual(incident.category_id, self.category)
        self.assertEqual(incident.lattitude, incident_data['lattitude'])
        self.assertEqual(incident.longitude, incident_data['longitude'])


class ZoneSerializerTestCase(TestCase):
    def test_zone_serializer(self):
        zone_data = {
            'name': 'Test Zone',
            'description': 'This is a test zone',
        }
        serializer = ZoneSerializer(data=zone_data)
        self.assertTrue(serializer.is_valid())
        zone = serializer.save()
        self.assertEqual(zone.name, zone_data['name'])
        self.assertEqual(zone.description, zone_data['description'])

class EluToZoneSerializerTestCase(TestCase):
    def setUp(self):
        self.elu = User.objects.create_user(
            email='elu@example.com',
            password='elupassword',
            first_name='Elu',
            last_name='User',
            user_type='elu'
        )
        self.zone = Zone.objects.create(
            name='Test Zone',
            description='Test Zone Description'
        )

    def test_elu_to_zone_serializer(self):
        data = {
            'elu': self.elu.id,
            'zone': self.zone.id,
        }
        serializer = EluToZoneSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        result = serializer.save()
        self.assertEqual(result['elu'], self.elu)
        self.assertEqual(result['zone'], self.zone)
        self.assertIn(self.zone, self.elu.zones.all())
