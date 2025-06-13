from django.test import TestCase
from unittest.mock import patch, MagicMock
from Mapapi.Send_mails import send_email
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

class SendMailsTests(TestCase):
    @patch('Mapapi.Send_mails.EmailMultiAlternatives')
    @patch('Mapapi.Send_mails.render_to_string')
    @patch('Mapapi.Send_mails.strip_tags')
    def test_send_email(self, mock_strip_tags, mock_render_to_string, mock_email_multi):
        # Setup test data
        subject = "Test Subject"
        template_name = "test_template.html"
        context = {"key": "value"}
        to_email = "test@example.com"
        
        # Setup mocks
        html_content = "<p>Test HTML Content</p>"
        text_content = "Test Text Content"
        mock_render_to_string.return_value = html_content
        mock_strip_tags.return_value = text_content
        
        # Create mock email instance
        mock_email_instance = MagicMock()
        mock_email_multi.return_value = mock_email_instance
        
        # Call the function
        send_email(subject, template_name, context, to_email)
        
        # Verify render_to_string was called correctly
        mock_render_to_string.assert_called_once_with(template_name, context)
        
        # Verify strip_tags was called correctly
        mock_strip_tags.assert_called_once_with(html_content)
        
        # Verify EmailMultiAlternatives was created correctly
        mock_email_multi.assert_called_once_with(
            subject,
            text_content,
            'Map Action <contact@map-action.com>',
            [to_email]
        )
        
        # Verify attach_alternative was called correctly
        mock_email_instance.attach_alternative.assert_called_once_with(html_content, "text/html")
        
        # Verify send was called
        mock_email_instance.send.assert_called_once()

    @patch('Mapapi.Send_mails.EmailMultiAlternatives')
    @patch('Mapapi.Send_mails.render_to_string')
    @patch('Mapapi.Send_mails.strip_tags')
    def test_send_email_with_error(self, mock_strip_tags, mock_render_to_string, mock_email_multi):
        # Setup test data
        subject = "Test Subject"
        template_name = "test_template.html"
        context = {"key": "value"}
        to_email = "test@example.com"
        
        # Setup mocks
        html_content = "<p>Test HTML Content</p>"
        text_content = "Test Text Content"
        mock_render_to_string.return_value = html_content
        mock_strip_tags.return_value = text_content
        
        # Setup mock to raise an exception
        mock_email_instance = MagicMock()
        mock_email_instance.send.side_effect = Exception("Test error")
        mock_email_multi.return_value = mock_email_instance
        
        # Call the function and verify it raises the exception
        with self.assertRaises(Exception):
            send_email(subject, template_name, context, to_email)
