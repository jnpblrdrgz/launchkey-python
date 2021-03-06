import unittest
from mock import MagicMock, ANY, patch
from uuid import uuid4
from json import dumps
from formencode import Invalid
from launchkey.transports.base import APIResponse
from launchkey.clients import ServiceClient
from launchkey.clients.service import AuthorizationResponse, SessionEndRequest, AuthPolicy
from launchkey.exceptions import LaunchKeyAPIException, InvalidParameters, InvalidPolicyInput, PolicyFailure, \
    EntityNotFound, RateLimited, RequestTimedOut, UnexpectedAPIResponse, UnexpectedDeviceResponse, UnexpectedKeyID, \
    InvalidGeoFenceName, InvalidPolicyFormat
from datetime import datetime
from ddt import ddt, data, unpack


class TestServiceClient(unittest.TestCase):

    def setUp(self):
        self._transport = MagicMock()
        self._response = APIResponse({}, {}, 200)
        self._transport.post.return_value = self._response
        self._transport.get.return_value = self._response
        self._transport.put.return_value = self._response
        self._transport.delete.return_value = self._response
        self._device_response = {"auth_request": str(uuid4()), "response": True, "device_id": str(uuid4()),
                                 "service_pins": ["1234", "3456", "5678"]}
        self._transport.loaded_issuer_private_key.decrypt.return_value = dumps(self._device_response)
        self._service_client = ServiceClient(uuid4(), self._transport)
        self._service_client._transport._verify_jwt_response = MagicMock()

    def test_authorize_success(self):
        self._response.data = {"auth_request": ANY}
        self._service_client.authorize(ANY, ANY, MagicMock(spec=AuthPolicy))

    def test_authorize_invalid_policy_input(self):
        self._response.data = {"auth_request": ANY}
        with self.assertRaises(InvalidParameters):
            self._service_client.authorize(ANY, ANY, ANY)

    def test_authorize_unexpected_result(self):
        self._response.data = {MagicMock(spec=str): ANY}
        with self.assertRaises(UnexpectedAPIResponse):
            self._service_client.authorize(ANY)

    def test_authorize_invalid_params(self):
        self._transport.post.side_effect = LaunchKeyAPIException({"error_code": "ARG-001", "error_detail": ""}, 400)
        with self.assertRaises(InvalidParameters):
            self._service_client.authorize(ANY)

    def test_authorize_invalid_policy(self):
        self._transport.post.side_effect = LaunchKeyAPIException({"error_code": "SVC-002", "error_detail": ""}, 400)
        with self.assertRaises(InvalidPolicyInput):
            self._service_client.authorize(ANY)

    def test_authorize_policy_failure(self):
        self._transport.post.side_effect = LaunchKeyAPIException({"error_code": "SVC-003", "error_detail": ""}, 400)
        with self.assertRaises(PolicyFailure):
            self._service_client.authorize(ANY)

    def test_authorize_entity_not_found(self):
        self._transport.post.side_effect = LaunchKeyAPIException({}, 404)
        with self.assertRaises(EntityNotFound):
            self._service_client.authorize(ANY)

    def test_authorize_rate_limited(self):
        self._transport.post.side_effect = LaunchKeyAPIException({}, 429)
        with self.assertRaises(RateLimited):
            self._service_client.authorize(ANY)

    @patch("launchkey.entities.service.b64decode")
    @patch("launchkey.entities.service.loads")
    @patch("launchkey.entities.service.AuthorizationResponsePackageValidator")
    def test_get_authorization_response_success(self, b64decode_patch, json_loads_patch,
                                                auth_response_package_validator_patch):
        b64decode_patch.return_value = MagicMock(spec=str)
        json_loads_patch.return_value = MagicMock(spec=dict)
        auth_response_package_validator_patch.return_value = MagicMock(spec=dict)
        public_key_id = str(uuid4())
        self._service_client._transport.loaded_issuer_private_keys = {public_key_id: MagicMock()}
        self._response.data = {
            "auth": ANY,
            "service_user_hash": ANY,
            "user_push_id": ANY,
            "org_user_hash": ANY,
            "public_key_id": public_key_id
        }
        self.assertIsInstance(self._service_client.get_authorization_response(ANY), AuthorizationResponse)

    def test_get_authorization_response_unexpected_response(self):
        self._response.data = {MagicMock(spec=str): ANY}
        with self.assertRaises(UnexpectedAPIResponse):
            self._service_client.get_authorization_response(ANY)

    def test_get_authorization_response_no_response(self):
        self._response.status_code = 204
        self.assertIsNone(self._service_client.get_authorization_response(ANY))

    def test_get_authorization_response_invalid_params(self):
        self._transport.get.side_effect = LaunchKeyAPIException({"error_code": "ARG-001", "error_detail": ""}, 400)
        with self.assertRaises(InvalidParameters):
            self._service_client.get_authorization_response(ANY)

    def test_get_authorization_response_timeout(self):
        self._transport.get.side_effect = LaunchKeyAPIException({}, 408)
        with self.assertRaises(RequestTimedOut):
            self._service_client.get_authorization_response(ANY)

    def test_session_start_success(self):
        self.assertIsNone(self._service_client.session_start(ANY, ANY))

    def test_session_start_invalid_params(self):
        self._transport.post.side_effect = LaunchKeyAPIException({"error_code": "ARG-001", "error_detail": ""}, 400)
        with self.assertRaises(InvalidParameters):
            self._service_client.session_start(ANY, ANY)

    def test_session_start_entity_not_found(self):
        self._transport.post.side_effect = LaunchKeyAPIException({}, 404)
        with self.assertRaises(EntityNotFound):
            self._service_client.session_start(ANY, ANY)

    def test_session_end_success(self):
        self.assertIsNone(self._service_client.session_end(ANY))

    def test_session_end_invalid_params(self):
        self._transport.delete.side_effect = LaunchKeyAPIException({"error_code": "ARG-001", "error_detail": ""}, 400)
        with self.assertRaises(InvalidParameters):
            self._service_client.session_end(ANY)

    def test_session_end_entity_not_found(self):
        self._transport.delete.side_effect = LaunchKeyAPIException({}, 404)
        with self.assertRaises(EntityNotFound):
            self._service_client.session_end(ANY)

    def test_webhook_session_end(self):
        request = dumps({"service_user_hash": str(uuid4()),
                         "api_time": str(datetime.utcnow())[:19].replace(" ", "T") + "Z"})
        self.assertIsInstance(self._service_client.handle_webhook(request, ANY), SessionEndRequest)

    def test_webhook_session_end_invalid_input(self):
        request = dumps({"service_user_hash": str(uuid4())})
        with self.assertRaises(UnexpectedAPIResponse):
            self.assertIsInstance(self._service_client.handle_webhook(request, ANY), SessionEndRequest)

    @patch("launchkey.entities.service.b64decode")
    @patch("launchkey.clients.service.loads")
    @patch("launchkey.entities.service.loads")
    @patch("launchkey.entities.validation.AuthorizeSSEValidator")
    @patch("launchkey.entities.service.AuthorizationResponsePackageValidator")
    def test_webhook_authorization_response(self, auth_response_package_validator_patch,
                                            auth_sse_validator_patch, json_loads_patch, json_loads_patch_2, b64decode_patch):
        b64decode_patch.return_value = MagicMock(spec=str)
        json_loads_patch.return_value = MagicMock(spec=dict)
        json_loads_patch_2.return_value = MagicMock(spec=dict)
        auth_sse_validator_patch.return_value = MagicMock(spec=dict)
        auth_response_package_validator_patch.return_value = MagicMock(spec=dict)
        self._transport.loaded_issuer_private_keys = {json_loads_patch_2().get(): MagicMock()}
        self.assertIsInstance(self._service_client.handle_webhook(MagicMock(), ANY), AuthorizationResponse)


class TestAuthorizationResponse(unittest.TestCase):

    def setUp(self):
        self.data = MagicMock()
        key_id = MagicMock()
        self.loaded_issuer_private_keys = {key_id: MagicMock()}
        self.data.get.return_value = key_id

    @patch("launchkey.entities.service.b64decode")
    @patch("launchkey.entities.service.loads")
    @patch("launchkey.entities.service.AuthorizationResponsePackageValidator")
    def test_authorization_response_success(self, b64decode_patch, json_loads_patch,
                                            auth_response_package_validator_patch):
        b64decode_patch.return_value = MagicMock(spec=str)
        json_loads_patch.return_value = MagicMock(spec=dict)
        auth_response_package_validator_patch.return_value = MagicMock(spec=dict)
        decrypted = b64decode_patch.to_python()
        response = AuthorizationResponse(self.data, self.loaded_issuer_private_keys)
        self.assertEqual(response.authorization_request_id, decrypted.get('auth_request'))
        self.assertEqual(response.authorized, decrypted.get('response'))
        self.assertEqual(response.device_id, decrypted.get('device_id'))
        self.assertEqual(response.service_pins, decrypted.get('service_pins'))
        self.assertEqual(response.service_user_hash, self.data.get('service_user_hash'))
        self.assertEqual(response.organization_user_hash, self.data.get('org_user_hash'))
        self.assertEqual(response.user_push_id, self.data.get('user_push_id'))

    @patch("launchkey.entities.service.b64decode")
    def test_decrypt_auth_package_base64_exception(self, b64decode_patch):
        b64decode_patch.side_effect = TypeError()
        with self.assertRaises(UnexpectedDeviceResponse):
            AuthorizationResponse(self.data, self.loaded_issuer_private_keys)

    @patch("launchkey.entities.service.b64decode")
    @patch("launchkey.entities.service.loads")
    def test_decrypt_auth_package_json_loads_exception(self, b64decode_patch, json_loads_patch):
        b64decode_patch.return_value = MagicMock(spec=str)
        json_loads_patch.side_effect = TypeError()
        with self.assertRaises(UnexpectedDeviceResponse):
            AuthorizationResponse(self.data, self.loaded_issuer_private_keys)

    @patch("launchkey.entities.service.b64decode")
    @patch("launchkey.entities.service.loads")
    @patch("launchkey.entities.service.AuthorizationResponsePackageValidator")
    def test_decrypt_auth_package_validator_exception(self, b64decode_patch, json_loads_patch,
                                                      auth_response_package_validator_patch):
        b64decode_patch.return_value = MagicMock(spec=str)
        json_loads_patch.side_effect = MagicMock(spec=dict)
        auth_response_package_validator_patch.side_effect = Invalid(ANY, ANY, ANY)
        with self.assertRaises(UnexpectedDeviceResponse):
            AuthorizationResponse(self.data, self.loaded_issuer_private_keys)

    def test_decrypt_auth_unexpected_key_id(self):
        with self.assertRaises(UnexpectedKeyID):
            AuthorizationResponse(self.data, {MagicMock(): MagicMock()})


@ddt
class TestPolicyObject(unittest.TestCase):

    @data(1, True, 0, False)
    def test_knowledge_factor_success(self, value):
        AuthPolicy(knowledge=value)

    @data(1, True, 0, False)
    def test_inherence_factor_success(self, value):
        AuthPolicy(inherence=value)

    @data(1, True, 0, False)
    def test_possession_factor_success(self, value):
        AuthPolicy(possession=value)

    @data(2, 3, 4, 5, None)
    def test_knowledge_factor_failure(self, value):
        with self.assertRaises(InvalidParameters):
            AuthPolicy(knowledge=value)

    @data(2, 3, 4, 5, None)
    def test_inherence_factor_failure(self, value):
        with self.assertRaises(InvalidParameters):
            AuthPolicy(inherence=value)

    @data(2, 3, 4, 5, None)
    def test_possession_factor_failure(self, value):
        with self.assertRaises(InvalidParameters):
            AuthPolicy(possession=value)

    def test_mixing_factor_requirements_exception(self):
        with self.assertRaises(InvalidParameters):
            AuthPolicy(any=1, knowledge=1, inherence=1, possession=1)

    def test_empty_policy_creation(self):
        policy = AuthPolicy()
        retrieved = policy.get_policy()
        self.assertIn('minimum_requirements', retrieved)
        self.assertEqual(retrieved['minimum_requirements'], [])

    @data(1, 2, 3, 4, 5)
    def test_setting_any_requirement(self, value):
        policy = AuthPolicy(any=value)
        self.assertEqual(policy.get_policy()['minimum_requirements'][0]['any'], value)

    def test_setting_specific_requirement(self):
        knowledge = 0
        inherence = 1
        possession = True
        policy = AuthPolicy(knowledge=knowledge, inherence=inherence, possession=possession)
        self.assertEqual(policy.get_policy()['minimum_requirements'][0]['knowledge'], int(knowledge))
        self.assertEqual(policy.get_policy()['minimum_requirements'][0]['inherence'], int(inherence))
        self.assertEqual(policy.get_policy()['minimum_requirements'][0]['possession'], int(possession))

    def test_jailbreak_protection_default(self):
        policy = AuthPolicy()
        self.assertEqual(len(policy.get_policy()['factors']), 1)
        self.assertEqual(policy.get_policy()['factors'][0]['factor'], 'device integrity')
        self.assertEqual(policy.get_policy()['factors'][0]['attributes']['factor enabled'], 0)

    def test_jailbreak_protection_true(self):
        policy = AuthPolicy(jailbreak_protection=True)
        retrieved = policy.get_policy()
        self.assertEqual(len(retrieved['factors']), 1)
        factor = retrieved['factors'][0]
        self.assertEqual(factor['factor'], 'device integrity')
        self.assertEqual(factor['attributes']['factor enabled'], 1)

    def test_add_geofence_success(self):
        policy = AuthPolicy()
        latitude = MagicMock(spec=int)
        longitude = MagicMock(spec=int)
        radius = MagicMock(spec=int)
        policy.add_geofence(latitude, longitude, radius)
        retrieved = policy.get_policy()
        self.assertEqual(len(retrieved['factors']), 2)
        factor = retrieved['factors'][1] if retrieved['factors'][1]['factor'] == 'geofence' else retrieved['factors'][0]
        self.assertEqual(factor['factor'], 'geofence')
        self.assertEqual(len(factor['attributes']['locations']), 1)
        location = factor['attributes']['locations'][0]
        self.assertEqual(location['latitude'], float(latitude))
        self.assertEqual(location['longitude'], float(longitude))
        self.assertEqual(location['radius'], float(radius))
        # Add a second geofence
        latitude2 = MagicMock(spec=int)
        longitude2 = MagicMock(spec=int)
        radius2 = MagicMock(spec=int)
        policy.add_geofence(latitude2, longitude2, radius2)
        retrieved = policy.get_policy()
        self.assertEqual(len(retrieved['factors']), 2)
        factor = retrieved['factors'][1] if retrieved['factors'][1]['factor'] == 'geofence' else retrieved['factors'][0]
        self.assertEqual(factor['factor'], 'geofence')
        self.assertEqual(len(factor['attributes']['locations']), 2)
        location = factor['attributes']['locations'][1]
        self.assertEqual(location['latitude'], float(latitude2))
        self.assertEqual(location['longitude'], float(longitude2))
        self.assertEqual(location['radius'], float(radius2))

    def test_add_geofence_invalid_input(self):
        policy = AuthPolicy()
        with self.assertRaises(InvalidParameters):
            policy.add_geofence(ANY, ANY, ANY)

    @data('myfence', 'my fence', '** fence 1234')
    def test_remove_geofence(self, name):
        policy = AuthPolicy()
        retrieved = policy.get_policy()
        self.assertEqual(len(retrieved['factors']), 1)
        self.assertEqual(policy.geofences, [])

        policy.add_geofence(MagicMock(spec=int), MagicMock(spec=int), MagicMock(spec=int), name)
        self.assertEqual(len(policy.geofences), 1)
        retrieved = policy.get_policy()
        self.assertEqual(len(retrieved['factors']), 2)
        self.assertEqual(len(retrieved['factors'][1]['attributes']['locations']), 1)

        policy.remove_geofence(name)
        self.assertEqual(policy.geofences, [])
        retrieved = policy.get_policy()
        self.assertEqual(len(retrieved['factors'][1]['attributes']['locations']), 0)

    def test_remove_invalid_geofence(self):
        policy = AuthPolicy()
        policy.add_geofence(1, 1, 2)
        with self.assertRaises(InvalidGeoFenceName):
            policy.remove_geofence(MagicMock(spec=str))

    def test_invalid_policy(self):
        policy = AuthPolicy()
        policy._policy['factors'].append(uuid4())
        with self.assertRaises(InvalidParameters):
            policy.get_policy()

    def test_eq_match(self):
        policy = AuthPolicy()
        policy.add_geofence(1, 2, 3, '123')
        policy2 = AuthPolicy()
        policy2.set_policy(policy.get_policy())
        self.assertEqual(policy, policy2)

    def test_eq_mismatch(self):
        policy = AuthPolicy()
        policy.add_geofence(1, 2, 3, '123')
        policy2 = AuthPolicy()
        self.assertNotEqual(policy, policy2)
        policy2.add_geofence(1, 2, 2, '122')
        self.assertNotEqual(policy, policy2)

    @data("test", {}, True, False, None)
    def test_eq_mismatch_non_object(self, value):
        policy = AuthPolicy()
        self.assertNotEqual(policy, value)

    def test_eq_mismatch_non_object_matching_policy(self):
        policy = AuthPolicy()
        self.assertNotEqual(policy, policy.get_policy())

    @data(True, False)
    def test_require_jailbreak_protection_new(self, status):
        policy = AuthPolicy()
        policy._policy['factors'] = []
        policy.require_jailbreak_protection(status)
        retrieved = policy.get_policy()
        self.assertEqual(len(retrieved['factors']), 1)
        self.assertEqual(retrieved['factors'][0]['attributes']['factor enabled'], 1 if status else 0)

    @data(True, False)
    def test_require_jailbreak_protection_existing(self, status):
        policy = AuthPolicy()
        policy.require_jailbreak_protection(status)
        retrieved = policy.get_policy()
        self.assertEqual(len(retrieved['factors']), 1)
        self.assertEqual(retrieved['factors'][0]['attributes']['factor enabled'], 1 if status else 0)

    def test_set_policy_dict(self):
        policy = AuthPolicy()
        self.assertEqual(len(policy.geofences), 0)
        policy.set_policy({'minimum_requirements': [], 'factors': []})

    def test_set_policy_json(self):
        policy = AuthPolicy()
        self.assertEqual(len(policy.geofences), 0)
        policy.set_policy(dumps({'minimum_requirements': [], 'factors': []}))

    def test_set_policy_invalid_json(self):
        with self.assertRaises(InvalidPolicyFormat):
            AuthPolicy().set_policy("{{{{Invalid JSON")

    @data({}, {'minimum_requirements': []}, {'factors': []})
    def test_set_policy_invalid(self, policy):
        with self.assertRaises(InvalidPolicyFormat):
            AuthPolicy().set_policy(policy)

    def test_set_policy_geofence(self):
        policy = AuthPolicy()
        self.assertEqual(len(policy.geofences), 0)
        policy.set_policy(
            {
                'minimum_requirements': [],
                'factors': [
                    {
                        'quickfail': False,
                        'priority': 1,
                        'requirement': 'forced requirement',
                        'attributes': {
                            'locations': [
                                {'latitude': 1.0, 'radius': 3.0, 'name': '123', 'longitude': 2.0}]},
                        'factor': 'geofence'
                    }
                ]
            }
        )
        self.assertEqual(len(policy.geofences), 1)
        self.assertEqual(policy.geofences[0].latitude, 1.0)
        self.assertEqual(policy.geofences[0].longitude, 2.0)
        self.assertEqual(policy.geofences[0].radius, 3.0)
        self.assertEqual(policy.geofences[0].name, '123')\


    @data(1, 0)
    def test_set_policy_jailbreak(self, enabled):
        policy = AuthPolicy()
        self.assertEqual(len(policy.geofences), 0)
        policy.set_policy(
            {
                'minimum_requirements': [],
                'factors': [
                    {
                        'quickfail': False,
                        'priority': 1,
                        'requirement': 'forced requirement',
                        'attributes': {'factor enabled': enabled},
                        'factor': 'device integrity'
                    }
                ]
            }
        )
        self.assertEqual(policy.jailbreak_protection, True if enabled else False)

    def test_set_minimum_requirments_all(self):
        policy = AuthPolicy()
        policy.set_policy(
            {
                'minimum_requirements': [
                    {
                        'possession': 1,
                        'requirement': 'authenticated',
                        'all': 1,
                        'inherence': 1,
                        'knowledge': 1
                    }
                ],
                'factors': []
            }
        )
        self.assertEqual(policy.minimum_amount, 1)
        self.assertIn('possession', policy.minimum_requirements)
        self.assertIn('inherence', policy.minimum_requirements)
        self.assertIn('knowledge', policy.minimum_requirements)

    @data((1, 1, 1, 1), (1, 1, 1, 0), (1, 1, 0, 1), (1, 0, 1, 1), (1, 0, 0, 1), (0, 0, 0, 0), (0, 0, 0, 1))
    @unpack
    def test_set_minimum_requirements(self, possession, inherence, knowledge, minimum_requirements):
        policy = AuthPolicy()
        policy.set_policy(
            {
                'minimum_requirements': [
                    {
                        'possession': possession,
                        'requirement': 'authenticated',
                        'any': minimum_requirements,
                        'inherence': inherence,
                        'knowledge': knowledge
                    }
                ],
                'factors': []
            }
        )
        self.assertEqual(policy.minimum_amount, minimum_requirements)
        if possession:
            self.assertIn('possession', policy.minimum_requirements)
        else:
            self.assertNotIn('possession', policy.minimum_requirements)
        if inherence:
            self.assertIn('inherence', policy.minimum_requirements)
        else:
            self.assertNotIn('inherence', policy.minimum_requirements)
        if knowledge:
            self.assertIn('knowledge', policy.minimum_requirements)
        else:
            self.assertNotIn('knowledge', policy.minimum_requirements)
