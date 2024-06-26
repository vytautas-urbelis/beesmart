import random

from django.contrib.auth import get_user_model
from django.core.mail import send_mail, EmailMultiAlternatives
from django.db.models import Count
from django.db.models.functions import TruncDay
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import CreateAPIView, UpdateAPIView, DestroyAPIView, RetrieveAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from datetime import timedelta
from django.utils import timezone

# from campaign.models import Campaign
from customer_user_profile.models import CustomerUserProfile
from email_layouts.get_card_email import get_card_layout
from email_layouts.qr_email import email_layout

from end_user_profile.models import EndUserProfile
from project.permissions import IsSelf
from project.settings import MEDIA_HOST, FRONT_END_HOST
from user.apple_pass import build_pass
from user.serializers import CustomerUserSerializer, UserRegistrationSerializer, EndUserSerializer, \
    CustomerUserUpdateDeleteSerializer, EndUserUpdateDeleteSerializer
# from django.core.mail import EmailMessage
from django.conf import settings
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from voucher.models import Voucher

User = get_user_model()


class TokenUserObtainView(TokenObtainPairView):
    """
    post:
    Create a new session for a user. Sends back tokens and user.
    """

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        user = User.objects.get(email=request.data['email'])
        req = request

        if user.is_customer:
            customer_serializer = CustomerUserSerializer(instance=user, context={'request': req})
            res = {
                'customer': customer_serializer.data,
                **serializer.validated_data
            }
            return Response(res, status=status.HTTP_200_OK)
        else:
            end_user_serializer = EndUserSerializer(instance=user, context={'request': req})
            res = {
                'endUser': end_user_serializer.data,
                **serializer.validated_data
            }
            return Response(res, status=status.HTTP_200_OK)


def code_generator(length=15):
    numbers = '0123456789qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM'
    return ''.join(random.choice(numbers) for _ in range(length))


class MeCustomerUser(RetrieveAPIView):
    """
    API view to retrieve the authenticated customer user's details.
    """
    serializer_class = CustomerUserSerializer

    def get(self, request, *args, **kwargs):
        """
        Retrieves the authenticated user's details and returns them.
        Uses a GET method to conform with the typical RESTful approach for data retrieval.
        """
        # Directly use the authenticated user from the request without additional database query
        serializer = CustomerUserSerializer(self.request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MeEndUser(RetrieveAPIView):
    """
    API view to retrieve the authenticated end user's details.
    """
    serializer_class = EndUserSerializer

    def get(self, request, *args, **kwargs):
        """
        Retrieves the authenticated user's details and returns them.
        Uses a GET method to conform with the typical RESTful approach for data retrieval.
        """
        # Directly use the authenticated user from the request without additional database query
        serializer = EndUserSerializer(self.request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class EndUserBySecretKey(RetrieveAPIView):
    """
    API view to retrieve the end user's details by secret_key.
    """
    serializer_class = EndUserSerializer
    permission_classes = []

    def get(self, request, *args, **kwargs):
        """
        Retrieves the authenticated user's details and returns them.
        Uses a GET method to conform with the typical RESTful approach for data retrieval.
        """
        # Directly use the authenticated user from the request without additional database query
        if EndUserProfile.objects.filter(secret_key=self.kwargs['secret_key']).exists():
            profile = EndUserProfile.objects.get(secret_key=self.kwargs['secret_key'])
            user = profile.user
            serializer = EndUserSerializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response('User doesn\'t exist', status=status.HTTP_404_NOT_FOUND)


# Create your views here.
class CreateCustomerUser(CreateAPIView):
    """
    API view to handle creation of customer user accounts.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = []  # letting all users access this endpoint

    def create(self, request, *args, **kwargs):
        """
        Overridden create method to add custom logic for user creation and sending an email with a registration code.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # Validate serializer data and raise an exception on failure.

        email = serializer.validated_data.get('email')

        if not email:
            return Response("No email provided", status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response('Customer user already exists', status=status.HTTP_400_BAD_REQUEST)

        # Create the user with the validated email. Assuming `is_customer` is a field on the User model.
        user = User.objects.create(email=email, username=email, is_customer=True)

        # Assuming `customer_user_profile` is created via signals or overridden save method on the User model.
        code = user.customer_user_profile.code

        send_mail(
            'Registration code:',
            f'generated code: {code}',
            'bee.smart.constructor@gmail.com',
            [email],
            fail_silently=False,
        )
        return Response("Code was generated and sent to your email", status=status.HTTP_200_OK)


class VeryfiCustomerUserView(UpdateAPIView):
    """
    API view to verify customer users using a code and update their user profile.
    """
    serializer_class = CustomerUserSerializer
    permission_classes = []  # letting all users access this endpoint

    def patch(self, request, *args, **kwargs):
        # Extract data from the request
        code = request.data.get('code')
        email = request.data.get('email')
        business_name = request.data.get('business_name')
        country = request.data.get('country')
        city = request.data.get('city')
        street = request.data.get('street')
        zip = request.data.get('zip')
        password = request.data.get('password')
        re_password = request.data.get('password_repeat')

        # Check if the provided passwords match, if not, return an error
        if password != re_password:
            return Response('Password does not match', status=status.HTTP_400_BAD_REQUEST)

        # Ensure all required fields are provided
        if not all([code, email, business_name, country, city, street, zip, password]):
            return Response('Missing required fields', status=status.HTTP_400_BAD_REQUEST)

        # Attempt to retrieve the user by email and verify the provided code
        try:
            user = User.objects.get(email=email)
            user_profile = CustomerUserProfile.objects.get(user=user)

            # Check if the code on the user profile matches the provided code
            if user.customer_user_profile.code == code:
                # Set the new password and save the user object
                user.set_password(password)
                user.save()

                # Update other user profile details and save
                user_profile.business_name = business_name
                user_profile.country = country
                user_profile.city = city
                user_profile.street = street
                user_profile.zip = zip
                user_profile.save()

                # Return a success response if everything is updated correctly
                return Response("User successfully verified", status=status.HTTP_200_OK)

            # Return an error if the verification code does not match
            return Response('Invalid verification code', status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            # Return an error if no user is found with the provided email
            return Response('This User does not exist.', status=status.HTTP_400_BAD_REQUEST)


class CreateEndUser(CreateAPIView):
    """
    API view to handle end-user registration. This view creates a new user or updates
    existing user's codes and sends a verification link via email.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = []  # letting all users access this endpoint

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # Validates incoming data and raises an exception on failure.

        email = serializer.validated_data.get('email')
        if not email:
            return Response("No email provided", status=status.HTTP_400_BAD_REQUEST)

        # Ensure the user profile is created, and generate new codes if the user was already in the system.
        if User.objects.filter(email=email).exists():
            user = User.objects.get(email=email)
            if CustomerUserProfile.objects.filter(user=user).exists():
                return Response("This email is already taken", status=status.HTTP_400_BAD_REQUEST)
            user_profile = EndUserProfile.objects.get(user=user)
            user_profile.code = code_generator()
            user_profile.secret_key = code_generator()
            user_profile.save()
            code = user_profile.code
        else:
            user = User.objects.create(email=email, username=email)
            code = user.end_user_profile.code

        # Prepare and send the email.
        send_mail(
            'BeeSmart email authentication',
            f'{MEDIA_HOST}/backend/api/enduser/user/verify/{code}',
            'bee.smart.constructor@gmail.com',
            [email],
            # html_message=f'<h1>WELCOME {MEDIA_HOST}/backend/api/enduser/user/verify/{code}</h1>',
            html_message=get_card_layout(FRONT_END_HOST, code, MEDIA_HOST),
            fail_silently=False,
        )
        return Response("Link was sent to your email", status=status.HTTP_200_OK)


class GenerateEndUserCard(CreateAPIView):
    """
    API view to generate a new QR code for an end user and send it via email.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = []  # letting all users access this endpoint

    def get_object(self):
        """
        Retrieve and return the EndUserProfile based on the provided 'code' in the URL.
        Overriding this method to include specific error handling and logic for code regeneration.
        """
        try:
            profile = EndUserProfile.objects.get(code=self.kwargs['generated_code'])
            profile.code = code_generator()  # Update the code on access
            profile.save(update_fields=['code'])
            return profile
        except EndUserProfile.DoesNotExist:
            # Handle case where profile does not exist to send a specific error response.
            raise NotFound('Profile with the given code does not exist.')

    def post(self, request, *args, **kwargs):
        """
        Overridden retrieve method to send an email with the QR code after successful retrieval
        and regeneration of the user's code.
        """
        data = self.request.data
        if data['password'] != data['password_repeat']:
            return Response({'Passwords didn\'t match'}, status=status.HTTP_400_BAD_REQUEST)
        profile = self.get_object()  # Get the object using the overridden get_object method.
        user = profile.user  # Access user directly from profile assuming a reverse relation from User to EndUserProfile.
        user.set_password(data['password'])
        user.save()
        secret_key = profile.secret_key

        def remove_domain(email):
            return email.split('@')[0] + '@'

        # Attempt to send an email with the QR code
        nickname = remove_domain(user.email)
        try:
            serial_nr = profile.serial_nr
            to_qr = f'"{secret_key}"'
            response = build_pass(nickname, serial_nr, to_qr, secret_key)

            # send_mail(
            #     'Registration code:',
            #     'Here is your updated QR code.',
            #     'from@example.com',  # Replace with your actual email or Django setting for default email.
            #     [user.email],
            #     html_message=email_layout(profile.qr_code.url, MEDIA_HOST, FRONT_END_HOST, secret_key),
            #     fail_silently=False,
            # )

            def send_email_with_attachment(subject, body, html_body, recipient_list, file_path):
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=recipient_list,
                )

                # Add an attachment
                with open(file_path, 'rb') as f:
                    email.attach(filename=file_path.split('/')[-1], content=f.read(),
                                 mimetype='application/vnd.apple.pkpass')  # Change mimetype as per the file type

                email.attach_alternative(html_body, "text/html")

                # Send the email
                email.send()

            # Example usage
            send_email_with_attachment(
                subject="Your QR and card",
                body='',
                html_body=email_layout(profile.qr_code.url, MEDIA_HOST, FRONT_END_HOST, secret_key),
                recipient_list=[user.email],
                file_path=f'passes/{nickname}.pkpass'
            )

            return response

            # serializer = EndUserSerializer(profile.user)  # Serialize user data
            # return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)  # Consider logging this instead of printing for production.
            return Response('Failed to send QR code. Please try again.', status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class EndUserCard(CreateAPIView):
    """
    API view to generate a new QR code for an end user and send it via email.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = []

    def get_object(self):
        """
        Retrieve and return the EndUserProfile based on the provided 'code' in the URL.
        Overriding this method to include specific error handling and logic for code regeneration.
        """
        try:
            secret_key = self.request.data['secret_key']
            profile = EndUserProfile.objects.get(secret_key=secret_key)
            return profile
        except EndUserProfile.DoesNotExist:
            # Handle case where profile does not exist to send a specific error response.
            raise NotFound('Profile does not exist.')

    def post(self, request, *args, **kwargs):
        """
        Overridden retrieve method to send an email with the QR code after successful retrieval
        and regeneration of the user's code.
        """
        profile = self.get_object()  # Get the object using the overridden get_object method.
        user = profile.user  # Access user directly from profile assuming a reverse relation from User to EndUserProfile.
        secret_key = profile.secret_key

        def remove_domain(email):
            return email.split('@')[0] + '@'

        # Attempt to send an email with the QR code
        nickname = remove_domain(user.email)
        try:
            serial_nr = profile.serial_nr
            to_qr = f'"{secret_key}"'
            response = build_pass(nickname, serial_nr, to_qr, secret_key)

            return response
        except Exception as e:
            print(e)  # Consider logging this instead of printing for production.
            return Response('Failed to send Apple card', status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeleteCustomerUser(DestroyAPIView):
    """
    API view to delete a CustomerUserProfile associated with the current authenticated user.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = [IsAuthenticated, IsSelf]
    queryset = CustomerUserProfile

    def get_object(self):
        # This method ensures that you retrieve the user's profile correctly.
        try:
            return User.objects.get(id=self.request.user.id)
        except User.DoesNotExist:
            raise Http404


class UpdateCustomerUser(UpdateAPIView):
    """
    API view to update a CustomerUserProfile for the currently authenticated user.
    """
    serializer_class = CustomerUserUpdateDeleteSerializer
    permission_classes = [IsAuthenticated, IsSelf]
    queryset = EndUserProfile.objects.all()

    def get_object(self):
        """
        Retrieve the CustomerUserProfile associated with the current authenticated user.
        This override ensures that we directly fetch the user's profile, raising Http404 if not found.
        """
        try:
            return CustomerUserProfile.objects.get(user=self.request.user)
        except CustomerUserProfile.DoesNotExist:
            raise Http404

    def patch(self, request, *args, **kwargs):
        """
        Handle the PATCH request to partially update the user's profile.
        """
        profile = self.get_object()  # Retrieve the user profile.
        serializer = self.serializer_class(profile, data=request.data, partial=True)  # Allow partial updates

        if serializer.is_valid():
            serializer.save()  # This automatically updates the profile instance
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            # Return errors if validation fails.
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateEndUser(UpdateAPIView):
    """
    API view to update a EndUserProfile for the currently authenticated user.
    """
    serializer_class = EndUserUpdateDeleteSerializer
    permission_classes = [IsAuthenticated, IsSelf]
    queryset = CustomerUserProfile.objects.all()

    def get_object(self):
        print('sssss')
        """
        Retrieve the CustomerUserProfile associated with the current authenticated user.
        This override ensures that we directly fetch the user's profile, raising Http404 if not found.
        """
        try:
            return EndUserProfile.objects.get(user=self.request.user)
        except EndUserProfile.DoesNotExist:
            raise Http404

    def patch(self, request, *args, **kwargs):
        """
        Handle the PATCH request to partially update the user's profile.
        """
        profile = self.get_object()  # Retrieve the user profile.
        serializer = self.serializer_class(profile, data=request.data, partial=True)  # Allow partial updates

        if serializer.is_valid():
            serializer.save()  # This automatically updates the profile instance
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            # Return errors if validation fails.
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserStampsCountView(ListAPIView):
    serializer_class = EndUserSerializer

    def get(self, request, *args, **kwargs):
        campaign_id = self.kwargs['campaign_id']

        # Get the counts for value_counted from 1 to 10
        counts = (
            EndUserProfile.objects
            .filter(collectors__campaign__id=campaign_id)
            .values('collectors__value_counted')
            .annotate(count=Count('user_id', distinct=True))
            .order_by('collectors__value_counted')
        )

        # Convert the queryset to a list of dictionaries
        data = [
            {'label': entry['collectors__value_counted'], 'number': entry['count']}
            for entry in counts if 1 <= entry['collectors__value_counted'] <= 10
        ]

        # Ensure that all labels from 1 to 10 are represented in the data
        labels_present = {entry['label'] for entry in data}
        data.extend([
            {'label': i, 'number': 0} for i in range(1, 11) if i not in labels_present
        ])

        # Sort the data by label to maintain the order from 1 to 10
        data.sort(key=lambda x: x['label'])

        return Response(data, status=status.HTTP_200_OK)


class UserVisitsCountView(ListAPIView):
    def get(self, request, *args, **kwargs):
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        campaign_id = kwargs['campaign_id']

        # Fetch counts in one query using annotations
        counts_queryset = (
            EndUserProfile.objects
            .filter(collectors__campaign__id=campaign_id,
                    collectors__logs_collectors__date_created__date__range=(thirty_days_ago, today))
            .annotate(date=TruncDay('collectors__logs_collectors__date_created'))
            .values('date')
            .annotate(count=Count('user__id'))  # add distinct=True to get uniq users
            .order_by('date')
        )

        # Convert datetime to date for consistent comparison
        counts_dict = {count['date'].date(): count['count'] for count in counts_queryset}

        # Prepare the response data, ensuring every day is represented
        data = [
            {'day': (thirty_days_ago + timedelta(days=i)).isoformat(),
             'number': counts_dict.get(thirty_days_ago + timedelta(days=i), 0)}
            for i in range(31)  # Ensure it covers exactly 30 days including today
            if counts_dict.get(thirty_days_ago + timedelta(days=i), 0) > 0
        ]
        return Response(data, status=status.HTTP_200_OK)


class NotClaimedVouchersView(ListAPIView):
    def get(self, request, *args, **kwargs):
        today = timezone.now().date()
        ten_weeks_ago = today - timedelta(days=70)  # 10 weeks back from today
        campaign_id = kwargs['campaign_id']

        # Fetch all vouchers within the last 5 weeks for the specific campaign that haven't been used
        vouchers = Voucher.objects.filter(
            campaign__id=campaign_id,
            is_used=False,
            date_created__date__range=(ten_weeks_ago, today)
        ).values('date_created__date')

        # Organize data by weeks
        week_counts = {}
        for voucher in vouchers:
            voucher_date = voucher['date_created__date']
            start_of_week = voucher_date - timedelta(days=voucher_date.weekday())  # Monday as the start of the week
            week_label = f"{start_of_week} - {start_of_week + timedelta(days=6)}"
            if week_label not in week_counts:
                week_counts[week_label] = 0
            week_counts[week_label] += 1

        # Create response data
        data = [{'label': week, 'number': week_counts.get(week, 0)} for week in
                sorted(week_counts.keys(), reverse=True)]

        return Response(data, status=status.HTTP_200_OK)


class UserPointsMoneyCountView(ListAPIView):
    serializer_class = EndUserSerializer

    def get(self, request, *args, **kwargs):
        campaign_id = self.kwargs['campaign_id']

        # campaign = Campaign.objects.get(id=campaign_id)
        # value_goal = campaign.value_goal

        # Get the counts for value_counted from 1 to 10
        counts = (
            EndUserProfile.objects
            .filter(collectors__campaign__id=campaign_id, collectors__is_collected=False)
            .values('collectors__value_counted')
            .annotate(count=Count('user_id', distinct=True))
            .order_by('collectors__value_counted')
        )

        # Convert the queryset to a list of dictionaries
        data = [
            {'label': entry['collectors__value_counted'], 'number': entry['count']}
            # for entry in counts if 1 <= entry['collectors__value_counted'] <= value_goal
            for entry in counts if entry['count'] > 0
        ]

        # Ensure that all labels from 0 to value_goal are represented in the data

        # labels_present = {entry['label'] for entry in data}
        # data.extend([
        #     {'label': i, 'number': 0} for i in range(10, int(value_goal), 10) if i not in labels_present
        # ])

        # Sort the data by label
        data.sort(key=lambda x: x['label'])

        return Response(data, status=status.HTTP_200_OK)
