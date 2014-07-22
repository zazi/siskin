help:
	@echo "make clean"

clean:
	rm -rf siskin.egg-info
	rm -rf build/ dist/
	rm -rf python-*.rpm

# packaging via vagrant
SSHCMD = ssh -o StrictHostKeyChecking=no -i vagrant.key vagrant@127.0.0.1 -p 2222

# Helper to build RPM on a RHEL6 VM, to link against glibc 2.12
vagrant.key:
	curl -sL "https://raw2.github.com/mitchellh/vagrant/mastekeys/vagrant" > vagrant.key
	chmod 0600 vagrant.key

vm-setup: vagrant.key
	$(SSHCMD) git clone https://github.com/miku/siskin.git

createrepo:
	cp dist/* /usr/share/nginx/html/repo/CentOS/6/x86_64
	createrepo /usr/share/nginx/html/repo/CentOS/6/x86_64

# run this target inside the CentOS6/libc2.12 VM
packages:
	git pull origin master
	cat requirements.txt | while read line; do fpm --verbose -s python -t rpm $$line; done
	cp python*rpm /vagrant/dist
