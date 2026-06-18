class position:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

    def set_position(self, x, y):
        self.x = x
        self.y = y

    def get_position(self):
        return (self.x, self.y)
    
create_pipeline_button = position(x=3573, y=176)

select_organization_field = position(x=1582, y=841)
select_organization_top_option = position(x=1682, y=937)

select_branch_field = position(x=1635, y=1018)
select_branch_top_option = position(x=1726, y=1117)

enter_company_name_field = position(x=1607, y=1194)

enter_address_field = position(x=1652, y=1375)

validate_and_create_button = position(x=2404, y=1558)

mi_json_field_4k_monitor = position(x=2274, y=2040)
mi_json_field_laptop_screen = position(x=1534, y=1495)
mi_json_field_1440p_monitor = position(x=1620, y=1296)

mi_json_field_vm = position(x=1212, y=949)


zoom_info_default_press_and_hold = position(x=943, y=690)
zoom_info_console_press_and_hold = position(x=957, y=445)

DEFAULT_MOUSE_MOVE_DURATION = 0.3
DEFAULT_TYPE_DURATION = 0.05
DEFAULT_ORGANIZATION = "First"
DEFAULT_BRANCH = "Sioux Falls - Sioux Falls, South Dakota"