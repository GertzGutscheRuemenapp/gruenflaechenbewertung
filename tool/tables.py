from gruenflaechenotp.base.project import ProjectTable
from gruenflaechenotp.base.database import Field


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
        geom = 'MultiPolygon'


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
    im_projektgebiet = Field(bool, False)

    class Meta:
        workspace = 'project'
        geom = 'MultiPolygon'


class Gruenflaechen(ProjectTable):

    class Meta:
        workspace = 'project'
        geom = 'MultiPolygon'


class GruenflaechenEingaenge(ProjectTable):

    class Meta:
        workspace = 'project'
        geom = 'Point'


class AdressenProcessed(ProjectTable):
    adresse = Field(int, 0)
    baublock = Field(int, 0)
    einwohner = Field(float, 0)
    in_projektgebiet = Field(bool, False)

    class Meta:
        workspace = 'results'
        geom = 'Point'


class GruenflaechenEingaengeProcessed(ProjectTable):
    eingang = Field(int, 0)
    gruenflaeche = Field(int, 0)

    class Meta:
        workspace = 'results'
        geom = 'Point'


class ProjektgebietProcessed(ProjectTable):

    class Meta:
        workspace = 'results'
        geom = 'MultiPolygon'


class AdressErgebnisse(ProjectTable):
    gruenflaeche_je_einwohner = Field(float, 0)
    einwohner = Field(float, 0)
    adresse = Field(int, 0)

    class Meta:
        workspace = 'results'
        geom = 'Point'


class BaublockErgebnisse(ProjectTable):
    gruenflaeche_je_einwohner = Field(float, 0)
    einwohner = Field(int, 0)
    baublock = Field(int, 0)

    class Meta:
        workspace = 'results'
        geom = 'MultiPolygon'




