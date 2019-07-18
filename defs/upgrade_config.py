from binilla.defs import upgrade_config

def upgrade_v2_to_v3(old_config, new_config):
    upgrade_config.upgrade_v1_to_v2(old_config, new_config)
    new_config.data.mozzarilla.parse(initdata=old_config.data.mozzarilla)

    return new_config
