def cambiar_modo_onu(onu_index="gpon-onu_1/13/2:1", modo="router", vlan_internet=200):
    """
    Cambia el modo de la ONU (router o bridge) sobre la VLAN de internet
    utilizando la conexión Telnet directa a la OLT ZTE.
    
    :param onu_index: Identificador de la ONU (ej. 'gpon-onu_1/13/2:1')
    :param modo: 'router' para NAT/VEIP o 'bridge' para entregarlo en puerto físico eth_0/1
    :param vlan_internet: ID de la VLAN de internet (por defecto 200)
    """
    modo = modo.lower()
    if modo not in ['router', 'bridge']:
        print("Modo no válido. Usa 'router' o 'bridge'.")
        return False

    try:
        net_connect = ConnectHandler(
            device_type='generic_termserver_telnet',
            host='10.99.99.2',
            port=23,
            global_delay_factor=2
        )

        # --- 1. PROCESO DE LOGIN MANUAL ---
        net_connect.read_until_pattern(r'Username:')
        net_connect.write_channel('cidi\r\n')

        net_connect.read_until_pattern(r'assword:')
        net_connect.write_channel('gpon1234\r\n')

        output = net_connect.read_until_pattern(r'[>#]')

        # --- 2. ENTRAR A MODO ENABLE ---
        if '>' in output:
            net_connect.write_channel('enable\r\n')
            net_connect.read_until_pattern(r'assword:')
            net_connect.write_channel('gpon1234\r\n')
            net_connect.read_until_pattern(r'#')

        # --- 3. DESACTIVAR PAGINACIÓN ---
        net_connect.write_channel('terminal length 0\r\n')
        net_connect.read_until_pattern(r'#')

        # --- 4. ACCEDER A LA GESTIÓN DE LA ONU ---
        net_connect.write_channel('configure terminal\r\n')
        net_connect.read_until_pattern(r'#')

        net_connect.write_channel(f'pon-onu-mng {onu_index}\r\n')
        net_connect.read_until_pattern(r'#')

        # --- 5. APLICAR CAMBIO DE MODO ---
        if modo == 'bridge':
            # Retira la VLAN del puerto virtual (cancela NAT) y la pasa al LAN 1
            net_connect.write_channel('no vlan port veip_1\r\n')
            net_connect.read_until_pattern(r'#')

            net_connect.write_channel(f'vlan port eth_0/1 mode hybrid def-vlan {vlan_internet}\r\n')
            net_connect.read_until_pattern(r'#')

        elif modo == 'router':
            # Retira la VLAN del LAN 1 y la pasa al puerto virtual VEIP (activa NAT)
            net_connect.write_channel('no vlan port eth_0/1\r\n')
            net_connect.read_until_pattern(r'#')

            net_connect.write_channel(f'vlan port veip_1 mode hybrid def-vlan {vlan_internet}\r\n')
            net_connect.read_until_pattern(r'#')

        # --- 6. SALIR Y GUARDAR MEMORIA ---
        net_connect.write_channel('exit\r\n')
        net_connect.read_until_pattern(r'#')

        net_connect.write_channel('exit\r\n')
        net_connect.read_until_pattern(r'#')

        net_connect.write_channel('write\r\n')
        net_connect.read_until_pattern(r'#')

        net_connect.disconnect()
        print(f"¡Éxito! La ONU {onu_index} se ha configurado en modo {modo.upper()}.")
        return True

    except Exception as e:
        print(f"Error al conmutar modo en OLT: {str(e)}")
        return False