from gruenflaechenotp.tool.base.project import ProjectTable
from gruenflaechenotp.tool.base.database import Field


class ProjectSettings(ProjectTable):
    required_green = Field(int, 6)
    max_walk_dist = Field(int, 500)
    project_buffer = Field(int, 250)
    router = Field(str, '')
    walk_speed = Field(float, 1.33)
    wheelchair = Field(bool, False)
    max_slope = Field(float, 0.083333)

    class Meta:
        workspace = 'project'


class Projektgebiet(ProjectTable):

    class Meta:
        workspace = 'project'
        geom = 'Polygon'


class Adressen(ProjectTable):
    strasse = Field(str, '')
    hausnummer = Field(str, '')
    ort = Field(str, '')
    beschreibung = Field(str, '')

    class Meta:
        workspace = 'project'
        geom = 'Point'


class Baubloecke(ProjectTable):
    einwohner = Field(int, 0)

    class Meta:
        workspace = 'project'
        geom = 'Polygon'


class Gruenflaechen(ProjectTable):

    class Meta:
        workspace = 'project'
        geom = 'Polygon'


class GruenflaechenEingaenge(ProjectTable):

    class Meta:
        workspace = 'project'
        geom = 'Point'