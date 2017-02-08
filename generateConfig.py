#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import yaml
import filecmp
import time
import pycurl
import hashlib
from jinja2 import Environment, FileSystemLoader
from logger import log
import helpers.system

# Define services and all parameters here
json_data = open(os.path.join(os.path.dirname(__file__), 'parameters.json'))
data = json.load(json_data)

# Read salt grains
with open("/etc/salt/grains") as stream:
    grains = yaml.load(stream)

# Load all services into services var
services = data['services']
# Load op5 servers into monitors var
monitors = data['monitors']
# Templates
templates = data['templates'][grains['env']]


# Upload config files function
def upload(monitor_url, monitor_token, hostname, location, configfile):
    c = pycurl.Curl()

    post_data = [("token", str(monitor_token)), ('servername', str(hostname)), ("location", str(location)), ("file", (c.FORM_FILE, configfile))]

    c.setopt(c.URL, str(monitor_url))
    c.setopt(c.POST, 1)
    c.setopt(c.HTTPPOST, post_data)
    c.setopt(pycurl.SSL_VERIFYPEER, 0)
    c.setopt(pycurl.SSL_VERIFYHOST, 0)
    c.perform()
    c.close()


# Render host section
def render_host_template(template_use, template_hostname, template_ip, template_project, template_app, template_environment, template_inckey):
    env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__))))
    template = env.get_template('templates/host.template')
    return template.render(template_use=template_use, template_hostname=template_hostname, template_ip=template_ip, template_project=template_project,
                           template_app=template_app, template_environment=template_environment, template_inckey=template_inckey)


# Render service section
def render_service_template(template_use, template_hostname, template_description, template_command,
                            template_environment, template_notification, template_project, template_app, template_inckey, template_graphite):
    env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__))))

    template = env.get_template('templates/service.template')
    return template.render(
        template_use=template_use,
        template_hostname=template_hostname,
        template_description=template_description,
        template_command=template_command,
        template_environment=template_environment,
        template_notification=template_notification,
        template_project=template_project,
        template_app=template_app,
        template_inckey=template_inckey,
        template_graphite=template_graphite
    )


# Render dependency
def render_dependency_template(dependency_hostname, dependency_name, dependency_services):
    env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__))))
    template = env.get_template('templates/dependency.template')
    return template.render(dependency_hostname=dependency_hostname, dependency_name=dependency_name, dependency_services=dependency_services)


# Write to file function
def write_to_file(path, content, mode):
    f = open(path, mode)
    f.write(content)
    f.close()


# return dependency dictionary
def dependency_list(*array):
    checks_array = array[0]
    dependencies = dict()

    for service, parameters in checks_array.iteritems():
        tmp_string = parameters['description'] + '.*'
        if parameters['dependency'] in dependencies:
            dependencies[parameters['dependency']].append(tmp_string)
        else:
            dependencies[parameters['dependency']] = []
            dependencies[parameters['dependency']].append(tmp_string)

    return dependencies


# Main function
if __name__ == "__main__":

    log.info("Running auto-op5-config")

    # Set default value if apps grain is not defined
    if grains['apps'] is None:
        grains_apps = ['none']
    else:
        grains_apps = grains['apps']

    # Array of config files that should be transfered
    files_to_transfer = []
    hostRendered = False
    # do not send config files by default
    transferConfigFiles = False
    # set hostname
    hostname = helpers.system.get_fqdn()
    # set IP of hostname
    host_ip = helpers.system.get_ip_address(helpers.system.get_interface_name())
    # path of config directory - /opt/monitor/auto-op5-config/configs
    config_directory = os.path.join(os.path.dirname(__file__), 'configs')

    # Create config directory
    if not os.path.exists(config_directory):
        log.info("Creating: " + config_directory)
        os.mkdir(config_directory)

    # Loop over services in parameters.json
    for service_type, service_name in services.iteritems():
        # check if type is in apps grains or type == system
        if service_type in grains['apps'] or service_type == "system":
            # define configuration files name
            conf_file_name = os.path.join(config_directory, str(hostname + "_" + service_type + ".cfg"))
            tmp_conf_file_name = os.path.join(config_directory, str(hostname + "_" + service_type + ".cfg.tmp"))

            # enable notifications only in PRD environment
            if grains['env'] == "prd" or grains['env'] == "stg":
                notifications = 1
            else:
                notifications = 0


            # loop over service checks defined in parameters.json
            for service_checks in service_name.keys():

                # grafana enable check
                try:
                    services[service_type][service_checks]['graphite']
                except KeyError:
                    graphite = 0
                else:
                    graphite = 1

                # system related service checks
                if service_type == "system":
                    # first render host section if not rendered yet
                    if not hostRendered:
                        host_inckey = hashlib.sha1(hostname).hexdigest()
                        render_host_parameters = render_host_template(templates['host'], hostname,
                                                                      host_ip, json.dumps(grains['project']), service_type, grains['env'], host_inckey)
                        write_to_file(tmp_conf_file_name, render_host_parameters, 'w')
                        hostRendered = True
                        log.info("Generating host template")

                    # assign parameters returned by helpers.system.init()
                    service_parameters = helpers.system.init(service_checks, services[service_type][service_checks])
                    # loop over returned service_parameters array
                    for key, value in service_parameters.iteritems():
                        service_inckey = hashlib.sha1(hostname + "-" +value['description']).hexdigest()
                        render_service_parameters = render_service_template(templates['service'],
                                                                            hostname,
                                                                            value['description'],
                                                                            value['command'],
                                                                            grains['env'],
                                                                            notifications,
                                                                            json.dumps(grains['project']),
                                                                            service_type,
                                                                            service_inckey,
                                                                            graphite)

                        log.info("Generating " + service_type + ":" + service_checks + " template")
                        write_to_file(tmp_conf_file_name, render_service_parameters, 'ab')

                # Render template without use of extra helpers
                else:
                    check_description = services[service_type][service_checks]['description']
                    check_command = services[service_type][service_checks]['command'] + \
                                    services[service_type][service_checks]['parameters']

                    service_inckey = hashlib.sha1(hostname + "-" + check_description).hexdigest()
                    render_check_parameters = render_service_template(templates['service'],
                                                                      hostname,
                                                                      check_description,
                                                                      check_command,
                                                                      grains['env'],
                                                                      notifications,
                                                                      json.dumps(grains['project']),
                                                                      service_type,
                                                                      service_inckey,
                                                                      graphite)

                    log.info("Generating " + service_type + ":" + service_checks + " template")
                    write_to_file(tmp_conf_file_name, render_check_parameters, 'w')



            #
            # Generate dependency
            #
            log.info("Render dependencies config file for: " + service_type)
            dependency_file_name = os.path.join(config_directory,
                                                str(hostname + "_" + service_type + "_dependency.cfg"))
            dependency_array = dependency_list(service_name)
            dependency_checks = ",".join(dependency_array['Check NRPE'])
            dependency_parameters = render_dependency_template(hostname, "Check NRPE", dependency_checks)
            write_to_file(dependency_file_name, dependency_parameters, 'w')
            files_to_transfer.append(dependency_file_name)

            #
            # Section responsible for comparing config files
            #

            if os.path.exists(conf_file_name):
                # compare tmp and current config files
                if filecmp.cmp(str(conf_file_name), str(tmp_conf_file_name), shallow=False):
                    # remove tmp file if config files are the same
                    os.remove(tmp_conf_file_name)
                # if files are different, backup and replace current config
                else:
                    log.info("Renaming old config as " + conf_file_name + "_" + time.strftime("%Y%m%d"))
                    os.rename(conf_file_name, conf_file_name + "_" + time.strftime("%Y%m%d"))
                    log.info("Creating new config file: " + conf_file_name)
                    os.rename(tmp_conf_file_name, conf_file_name)
                    # Config files should be transfered
                    transferConfigFiles = True
                    files_to_transfer.append(conf_file_name)
            # if config file does not exist, create it
            else:
                log.info("Creating new config file: " + conf_file_name)
                os.rename(tmp_conf_file_name, conf_file_name)
                transferConfigFiles = True
                files_to_transfer.append(conf_file_name)

    # Upload files
    if transferConfigFiles:
        log.info("Uploading files")
        for item in files_to_transfer:
            upload(monitors[grains['loc']]['url'],
                   monitors[grains['loc']]['token'],
                   hostname,
                   grains['loc'],
                   item)

