# coding=utf-8
from rest_framework import response, permissions
from rest_framework.schemas import SchemaGenerator
from rest_framework.renderers import CoreJSONRenderer
from rest_framework.views import APIView

from drf_openapi.codec import OpenAPIRenderer, SwaggerUIRenderer
from drf_openapi.entities import OpenApiSchemaGenerator


class SchemaView(APIView):

    def __init__(self,
                 url='',
                 title='API Documentation',
                 renderer_classes=(CoreJSONRenderer, SwaggerUIRenderer, OpenAPIRenderer),
                 permission_classes=(permissions.IsAdminUser,),
                 generator_class=OpenApiSchemaGenerator,
                 **generator_class_kwargs):
        if not issubclass(generator_class, SchemaGenerator):
            raise Exception('Generator class must extend rest_framework.schemas.SchemaGenerator')
        self.generator_class=generator_class
        self.generator_class_kwargs = generator_class_kwargs
        super(SchemaView, self).__init__(url=url, title=title, renderer_classes=renderer_classes, permission_classes=permission_classes)

    def get(self, request, version):
        generator = self.generator_class(
            version=version,
            url=self.url,
            title=self.title,
            **self.generator_class_kwargs
        )
        return response.Response(generator.get_schema(request))
