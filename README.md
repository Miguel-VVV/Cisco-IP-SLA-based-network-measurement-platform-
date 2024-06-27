This application combines Cisco IP SLA with Logstash, ElasticSearch and Grafana to create a platform that allows the user to visualize statistics of a network that contains Cisco Routers.
Pre-Requirements:
  - Logstash has to be installed and running in the same machine as the platform is being executed on.
  - Instances of both Grafana and ElasticSearch have to be running (these can be on different machines).
  - The platform needs the a token from the Grafana API, together with the username, password and Certificate for ElasticSearch.
