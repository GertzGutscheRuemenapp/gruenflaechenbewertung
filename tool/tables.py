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