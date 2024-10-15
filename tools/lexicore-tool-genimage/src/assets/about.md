# Image generation

## Description
The Gen-Image Tool API provides method for creating images from scratch based on a text prompt.
You can request 1 image at a time

## Usage
Creates an image given a prompt.
```
POST https://host/v1/images/generations
```
### Request body


| Field name | Type   | Required | Description                                                                         |
|------------|--------|----------|-------------------------------------------------------------------------------------|
| prompt     | string | Required | A text description of the desired image(s). The maximum length is 4000 characters . |

### Response body
| Field name | Type   | Required | Description                      |
|------------|--------|----------|----------------------------------|
| imageUrl   | string | Required | The URL of the generated image   |

### Example request
```cURL
curl --location 'http://localhost:3000/gen-image/generate' \
--header 'Content-Type: application/json' \
--data '{"prompt": "generate image of german shepherd"}'
```
### Example response

```json
{
    "imageUrl": "https://oaidalleapiprodscus.blob.core.windows.net/private/org-SHIR7w8y0dNgpDdhnsOAiifk/user-zza1BOkkpDslw4Cbc0Tw3dsj/img-6zkMwjYkcaSGWQKly6D4Fogq.png?st=2024-09-08T14%3A50%3A19Z&se=2024-09-08T16%3A50%3A19Z&sp=r&sv=2024-08-04&sr=b&rscd=inline&rsct=image/png&skoid=d505667d-d6c1-4a0a-bac7-5c84a87759f8&sktid=a48cca56-e6da-484e-a814-9c849652bcb3&skt=2024-09-07T22%3A14%3A14Z&ske=2024-09-08T22%3A14%3A14Z&sks=b&skv=2024-08-04&sig=f7UfyVjlkhpE8HpIu1SHrL9TXcqFkiDkGPvIo/sIsTU%3D"
}
```
