
import re
import yaml
from netmiko import ConnectHandler

# ==========================================
# 1. EXTRACCIÓN AUTOMÁTICA OLT ZTE (RAW MODE)
# ==========================================
def obtener_datos_olt():
    datos_olt = {
        'hostname': 'ZXAN',
        'interfaces': [],
        'onus_registradas': []
    }

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

        # --- 3. EXTRACCIÓN DE DATOS (MODO DIRECTO) ---
        # Desactivamos la paginación por si la OLT requiere "Enter" para ver más texto
        net_connect.write_channel('terminal length 0\r\n')
        net_connect.read_until_pattern(r'#')

        net_connect.write_channel('show interface mng1\r\n')
        out_mng = net_connect.read_until_pattern(r'#')

        net_connect.write_channel('show vlan brief\r\n')
        out_vlans = net_connect.read_until_pattern(r'#')

        net_connect.write_channel('show gpon onu state\r\n')
        out_onus = net_connect.read_until_pattern(r'#')

        # separacion de interfaces
        datos_olt['interfaces'].append({
            'nombre': 'mng1',
            'raw_status': out_mng.splitlines()[:3]
        })

        # separacion de ONUs
        for line in out_onus.splitlines():
            if 'gpon-onu' in line:
                partes = line.split()
                datos_olt['onus_registradas'].append({
                    'onu_id': partes[0],
                    'estado': partes[-1] if len(partes) > 1 else 'unknown'
                })

        net_connect.disconnect()

    except Exception as e:
        datos_olt['error'] = f"Error en extracción manual de OLT: {str(e)}"

    return datos_olt

# ==========================================
# 2. EXTRACCIÓN AUTOMÁTICA MIKROTIK (SSH)
# ==========================================
def obtener_datos_mikrotik():
    # Parámetros de conexión SSH al MikroTik
    mk_device = {
        'device_type': 'mikrotik_routeros',
        'host': '192.168.10.1', # IP actual de ether1 en la maqueta
        'username': 'admin',
        'password': '123',        # Tu contraseña de MikroTik
        'conn_timeout': 20,       
        'auth_timeout': 20,
        'global_delay_factor': 2,
    }

    datos_mk = {
        'interfaces': [],
        'routes': [],
        'dhcp_server': []
    }

    try:
        net_connect = ConnectHandler(**mk_device)
        
        # Ejecutar comandos de exportación e inspección en MikroTik
        print_ip = net_connect.send_command('/ip address print terse')
        print_route = net_connect.send_command('/ip route print terse')
        print_dhcp = net_connect.send_command('/ip dhcp-server network print terse')

        # Extraer direcciones IP dinámicamente
        for line in print_ip.splitlines():
            if 'address=' in line:
                datos_mk['interfaces'].append({'raw_config': line.strip()})

        # Extraer rutas dinámicamente
        for line in print_route.splitlines():
            if 'dst-address=' in line:
                datos_mk['routes'].append({'raw_route': line.strip()})

        net_connect.disconnect()
    except Exception as e:
        datos_mk['error'] = f"No se pudo conectar al MikroTik automáticamente: {str(e)}"

    return datos_mk


# ==========================================
# 3. GENERACIÓN DEL ARCHIVO YAML FINAL
# ==========================================
def generar_yaml_completo():
    print("Conectándose a los equipos de la maqueta y extrayendo configuración...")
    
    configuracion_maqueta = {
        'maqueta_auto_extracted': {
            'mikrotik_principal': obtener_datos_mikrotik(),
            'olt_zte': obtener_datos_olt()
        }
    }

    # Guardar automáticamente en el archivo YAML
    with open('maqueta_config.yaml', 'w', encoding='utf-8') as f:
        yaml.dump(configuracion_maqueta, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print("\n¡Listo! El archivo 'maqueta_config.yaml' se ha generado automáticamente leyendo la maqueta.")

if __name__ == '__main__':
    generar_yaml_completo()


def generar_yaml_completo():
    print("Conectándose a los equipos de la maqueta y extrayendo configuración...\n")
    
    configuracion_maqueta = {
        'maqueta_auto_extracted': {
            'mikrotik_principal': obtener_datos_mikrotik(),
            'olt_zte': obtener_datos_olt()
        }
    }

    # Convertir los datos a formato de texto YAML
    resultado_texto = yaml.dump(
        configuracion_maqueta, 
        default_flow_style=False, 
        allow_unicode=True, 
        sort_keys=False
    )

    # Imprimir el resultado directamente en el CMD
    print("=== CONFIGURACIÓN EXTRAÍDA ===")
    print(resultado_texto)
    print("==============================")

if __name__ == '__main__':
    generar_yaml_completo()






