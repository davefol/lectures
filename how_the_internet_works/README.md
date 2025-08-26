# How the internet works (roughly)

## Ethernet (layer 2 frames)

There is a house of computers called Montague.

Each computer in the Montague house has a name, we call this a MAC address (12 hex characters or 48 bits). 

Romeo can send a message to Benvolio, another computer in the Montague house by sending an Ethernet frame.

The ethernet frame consists of 
1. destination MAC address
  - the name of the target of the message, in this case Benvolio
2. source MAC address
  - the name of the source of the message, in this case Romeo
3. message type
  - for now we'll only care about 0x0800 and 0x0806 which we'll learn about later
4. message data
  - will depend on the message type and will be some higher layer protocol which we'll learn about later
5. CRC
  - a check to make sure the data didn't get messed up on the way


## Ethernet (layer 1 bits/symbols)
To actually send a message, Romeo puts the message "on the wire", usually a Cat6 cable with RJ45 connectors
on both end, what we colloqially call an "ethernet cable". 

The actual characteristics of this electrical signal depend on the speed of the ethernet and we wont be
getting into it for this lecture.

In any case, Romeo, who we call a "host", drives some of the copper wires high and low and at the other end
is a switch.

## Switching

The switch does a simple job, it matches ethernet frames from one port to another, what we call "switching".

To do this, it keeps track of a table mapping ports to MAC addresses. 

When Romeo sends an ethernet frame, the switch does "learning", recording the fact that, lets say port 1 is connected
to Romeo (Romeo's MAC address).

It doesnt know what port is Benvolio so it just sends the message to all the ports. This is called flooding.

When Benvolio responds, the switch "learns" that Benvolio is on port 2. It already knows that Romeo
is on port 1 so it "forwads" the ethernet frame, sending it directly to Romeo instead of to every port.

Through learning, flooding, forwarding, and keeping track of which MAC address goes to which port, the switch
does its job.

## Internet Protocol (layer 3 packets)

While MAC addresses allow the switch to disambiguate between different devices, they are a very flat structure.
They can only tell you that two things are definitely different.

It would be useful to have an address that is hierarchical. This helps solve a problem we are about to run into,
how to communicate with other networks.

The hieararchy will be network based and will help us distinguish and communicate between networks so we will
refer to this protocol as the inter-network protocol or internet for short.

There are two major versions of the internet protocol. v4 and v6. For simplicity we'll look at v4.

### Address resolution protocol (layer 3 packets)

If Romeo wants to send Benvolio an IPv4 packet, he still needs to know his MAC address. The switch doesn't know anything
about IP, all it knows is MAC addresses and ethernet packets.

What Romeo can do is send an ethernet frame with a message to a special MAC address known as the broadcast address (FF:FF:FF:FF:FF:FF).
This will be sent to all devices. The data can contain a query like "whoever's IP address is X, please let me know your
MAC address so that I can send you messages".

This type of messages is called an ARP packet (Address resolution protocol).

The packet format is
1. hardware type (we care about type 1 which is ethernet)
2. protocol type (we care about 0x0800 which is IPv4)
3. hardware length (6 for ethernet - remember mac address is 12 hex characters, 6 bytes, 48 bits)
4. protocol length (4 for IPv4, normally we write this as 4 bytes separated by periods)
5. operation (1 for request, 2 for reply)
6. sender hardware address (MAC address)
7. sender protocol address (IP address)
8. target hardware address (nothing for request, origin for reply)
9. target protocol address (IP address)

We put all of this inside the data portion of an ethernet frame. We also mark the type in the ethernet frame
header as 0x0806 (remember 0x0800 is for IPv4)

The idea of putting a higher layer protocol entirely in the data portion of a lower layer protocol is called
encapsulation and will happen all the way up the layers.

Romeo will send an ARP packet and Benvolio will respond with an ARP packet, then Romeo will have the 
MAC address of Benvolio and will be able to send him IPv4 packets.

### Subnet masks and default gateways

But how does Romeo know that Benvolio is in his network? This is the problem that IP solves.

Romeo can apply his subnet mask to determine if any IP address is in his local network.

For example, say Romeo's IP address is 192.168.1.3 and Benvolio's is 192.168.1.14.
Romeo's subnet mask is 255.255.255.0. If we and Romeo's IP address with the subnet mask we get 192.168.1.0.
If we do the same to Benvolio's IP address we also get 192.168.1.0. Since these are the same, they 
must be in the same local network and we can do the process we described above where we discover the MAC address
using ARP then use that to send an ethernet frame containing our IP packet.

The subnet mask defines the "local network".

What about if Romeo wants to send a message to Juliet?. She is in the Capulet network so here IP address
is 192.168.7.5 and if we AND it with the subnet mask we get 192.168.7.0 which is different from Romeo's
IP address.

In this case the best Romeo can do is send the message to Juliet's nurse. The nurse is special
because she is a "gateway" or a device that is connected between to networks. She is also a "router" which
is a device that forwards IP packets.

The nurse is Romeo's default gateway so whenever Romeo needs to send a message to anyone not in his network 
he sends it to the nurse who's IP he has filed under "default gateway" as 192.168.1.1.

He sends an ARP request, gets the nurses MAC address and sends her an ethernet frame with the IP packet
addressed to Juliet.

So the IP packet he sends has
1. A bunch of header info
2. Source IP address
3. Destination IP address
4. Options (rarely used)
5. Data

I'd like to reiterate that in this case, Romeo is sending an ethernet frame to the nurse with 
his MAC address and the source and the nurse's MAC address as the destination. Inside of the data
of that frame he is sending an IPv4 packet with his IP address as the source and Juliet's IP address
as the destination.

### Routing
The switch will forward (or flood) the ethernt frame to the nurse who will then strip the ethernet
frame off of the packet leaving just the IP packet.

She will then go through the routing procedure, checking if the IP matches a pattern in her routing table,
forwarding it if it does and dropping if it doesnt.

In this case, because she is directly connected to both the Montague and the Capulet networks, 
she will have a directly connected route in her routing table. This route basically says "any IP
packet intended for somewhere in the Capulet network should go out on this interface". Where interface
is the physical ethernet connection to the Capulet switch.

In this case, it is, so she makes an ARP request for Juliet, receives back her MAC address then creates
a new ethernet frame addressed to juliet from her (the nurse) and stuffs the IP packet in the frame as is.

This processes of taking the IP address out of an ethernet frame, inspecting it, then putting it into a new
ethernet frame that gets it closer to the intended recipient is called routing.

