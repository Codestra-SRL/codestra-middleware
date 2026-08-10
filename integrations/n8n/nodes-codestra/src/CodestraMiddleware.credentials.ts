export class CodestraMiddleware {
  name = 'codestraMiddleware';
  displayName = 'Codestra Middleware Service';
  documentationUrl = 'https://middleware.codestra.co/docs';
  properties = [
    { displayName: 'Base URL', name: 'baseUrl', type: 'string', default: 'https://middleware.codestra.co', required: true },
    { displayName: 'Service Token', name: 'serviceToken', type: 'string', typeOptions: { password: true }, default: '', required: true },
    { displayName: 'HMAC Secret', name: 'hmacSecret', type: 'string', typeOptions: { password: true }, default: '', required: true },
  ];
}
