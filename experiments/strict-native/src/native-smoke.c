/* Separate XNS1 smoke-test, not the existing IPvX encrypted mesh protocol.
 * Guest mode uses Ed25519 proof of key possession and first-seen role binding.
 * Role labels/CRC are not authentication; TOFU is not admission or confidentiality.
 * The portable host self-test omits guest mode and Ed25519 unless XNS_CRYPTO is set. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define TYPE 0x88b5
#define HEADER 188
#define MAX_PAYLOAD 1300
#define TASK 1
#define RESULT 2
#define HELLO 3
#define CASES 16

#ifdef XNS_CRYPTO
#include <openssl/evp.h>
#include <openssl/sha.h>
static EVP_PKEY *identity;
static uint8_t public_key[32],node_id[32],peer_ids[4][32];
static int peer_known[4];
static void hex(const uint8_t *bytes,size_t n,char *text) { for(size_t i=0;i<n;i++)sprintf(text+i*2,"%02x",bytes[i]); }
static int keygen(void) {
    EVP_PKEY_CTX *ctx=EVP_PKEY_CTX_new_id(EVP_PKEY_ED25519,NULL);
    int ok=ctx && EVP_PKEY_keygen_init(ctx)>0 && EVP_PKEY_keygen(ctx,&identity)>0;EVP_PKEY_CTX_free(ctx);
    size_t n=32;if(!ok || EVP_PKEY_get_raw_public_key(identity,public_key,&n)<=0 || n!=32)return 0;
    SHA256(public_key,32,node_id);return 1;
}
static int signature(uint8_t *p,size_t n,int sign) {
    uint8_t input[HEADER+MAX_PAYLOAD];memcpy(input,p,n);input[6]=0;memset(input+24,0,4);memset(input+124,0,64);
    EVP_PKEY *key=sign?identity:EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519,NULL,p+92,32);
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();int ok=0;size_t length=64;
    if(key && ctx) {
        if(sign)ok=EVP_DigestSignInit(ctx,NULL,NULL,NULL,key)>0 && EVP_DigestSign(ctx,p+124,&length,input,n)>0 && length==64;
        else ok=EVP_DigestVerifyInit(ctx,NULL,NULL,NULL,key)>0 && EVP_DigestVerify(ctx,p+124,64,input,n)>0;
    }
    EVP_MD_CTX_free(ctx);if(!sign)EVP_PKEY_free(key);return ok;
}
#endif

static uint32_t get32(const uint8_t *p) { return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3]; }
static void put32(uint8_t *p,uint32_t n) { p[0]=(uint8_t)(n>>24);p[1]=(uint8_t)(n>>16);p[2]=(uint8_t)(n>>8);p[3]=(uint8_t)n; }
static uint16_t get16(const uint8_t *p) { return (uint16_t)(((unsigned)p[0]<<8)|p[1]); }
static void put16(uint8_t *p,uint16_t n) { p[0]=(uint8_t)(n>>8);p[1]=(uint8_t)n; }
static uint32_t checksum(const uint8_t *p,size_t n) {
    uint32_t c=0xffffffffU;
    for(size_t i=0;i<n;i++) { uint8_t b=(i>=24 && i<28)?0:p[i];c^=b;for(int j=0;j<8;j++)c=(c>>1)^(0xedb88320U & (uint32_t)-(int)(c&1)); }
    return ~c;
}
static size_t encode_bytes(uint8_t *p,int kind,int hops,uint32_t seq,uint32_t src,uint32_t dst,const uint8_t *payload,size_t n) {
    if(n>MAX_PAYLOAD)return 0;
    memset(p,0,HEADER);memcpy(p,"XNS1",4);p[4]=1;p[5]=(uint8_t)kind;p[6]=(uint8_t)hops;
    put32(p+8,seq);put32(p+12,src);put32(p+16,dst);put16(p+20,(uint16_t)n);memcpy(p+HEADER,payload,n);
    #ifdef XNS_CRYPTO
    memcpy(p+28,node_id,32);memcpy(p+92,public_key,32);
    if(dst>0 && dst<4 && peer_known[dst])memcpy(p+60,peer_ids[dst],32);
    if(!signature(p,HEADER+n,1))return 0;
    #endif
    put32(p+24,checksum(p,HEADER+n));return HEADER+n;
}
static size_t encode(uint8_t *p,int kind,int hops,uint32_t seq,uint32_t src,uint32_t dst,const char *payload) { return encode_bytes(p,kind,hops,seq,src,dst,(const uint8_t*)payload,strlen(payload)); }
static int valid(const uint8_t *p,size_t n) {
    if(n<HEADER || memcmp(p,"XNS1",4) || p[4]!=1 || (p[5]!=TASK && p[5]!=RESULT && p[5]!=HELLO)
       || p[6]==0 || p[6]>8 || p[7] || p[22] || p[23])return 0;
    size_t length=get16(p+20);if(length>MAX_PAYLOAD || HEADER+length>n || get32(p+24)!=checksum(p,HEADER+length))return 0;
    #ifdef XNS_CRYPTO
    uint8_t id[32];SHA256(p+92,32,id);if(memcmp(id,p+28,32))return 0;
    if(!signature((uint8_t*)p,HEADER+length,0))return 0;
    #endif
    return 1;
}
static int selftest(void) {
    #ifdef XNS_CRYPTO
    if(!keygen())return 10;
    #endif
    uint8_t p[HEADER+MAX_PAYLOAD];size_t n=encode(p,TASK,3,42,1,2,"SUM 17 25");
    if(!valid(p,n)||get32(p+8)!=42||get16(p+20)!=9)return 1;
    p[HEADER]^=1;if(valid(p,n))return 2;p[HEADER]^=1;
    if(valid(p,HEADER-1))return 3;
    p[6]=0;if(valid(p,n))return 4;
    #ifdef XNS_CRYPTO
    p[6]=3;put32(p+24,checksum(p,n));p[HEADER]^=1;put32(p+24,checksum(p,n));if(valid(p,n))return 11;
    puts("PASS: wire bounds, CRC and Ed25519 reject a changed payload even with recomputed CRC; guest execution not asserted");
    #else
    puts("PASS: portable wire bounds and CRC tests only; Ed25519 and guest execution not compiled in this host test");
    #endif
    return 0;
}

#ifdef __linux__
#include <fcntl.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/socket.h>
#include <linux/if.h>
#include <linux/if_ether.h>
#include <linux/if_packet.h>

struct link { int fd,index;uint8_t mac[6],peer[6];const char *name; };
static char role='?';
static uint32_t role_id(void) { return role=='A'?1:role=='B'?2:3; }
static void fail(const char *step) { printf("XNS_EVENT {\"node\":\"%c\",\"event\":\"failure\",\"step\":\"%s\",\"errno\":%d}\n",role,step,errno);fflush(stdout);reboot(RB_AUTOBOOT);for(;;)pause(); }
static uint16_t network16(uint16_t n) { uint8_t b[2];put16(b,n);uint16_t out;memcpy(&out,b,2);return out; }
static double seconds(void) { struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))fail("clock");return (double)t.tv_sec+(double)t.tv_nsec/1e9; }
static void probe(void) {
    const int families[]={AF_INET,AF_INET6};const char *names[]={"AF_INET","AF_INET6"};
    const int types[]={SOCK_STREAM,SOCK_DGRAM};const char *kinds[]={"stream","datagram"};
    for(int i=0;i<2;i++)for(int j=0;j<2;j++) {
        errno=0;int fd=socket(families[i],types[j],0),saved=errno;if(fd>=0)close(fd);
        int ok=fd<0 && saved==EAFNOSUPPORT;
        printf("XNS_EVENT {\"node\":\"%c\",\"event\":\"socket_probe\",\"family\":\"%s\",\"kind\":\"%s\",\"rejected\":%s,\"errno\":%d}\n",role,names[i],kinds[j],ok?"true":"false",saved);
        if(!ok)fail("IP_family_available");
    }
    int pair[2];if(socketpair(AF_UNIX,SOCK_STREAM,0,pair))fail("AF_UNIX");close(pair[0]);close(pair[1]);
    printf("XNS_EVENT {\"node\":\"%c\",\"event\":\"unix_probe\",\"available\":true}\n",role);
    if(access("/proc/net/route",F_OK)==0 || access("/proc/net/if_inet6",F_OK)==0)fail("IP_proc_state_exists");
}
static void openlink(struct link *link,const char *name,const uint8_t peer[6]) {
    memset(link,0,sizeof(*link));link->name=name;memcpy(link->peer,peer,6);
    link->fd=socket(AF_PACKET,SOCK_RAW,network16(TYPE));if(link->fd<0)fail("AF_PACKET");
    struct ifreq req;memset(&req,0,sizeof(req));snprintf(req.ifr_name,sizeof(req.ifr_name),"%s",name);
    if(ioctl(link->fd,SIOCGIFINDEX,&req))fail("interface_index");link->index=req.ifr_ifindex;
    if(ioctl(link->fd,SIOCGIFHWADDR,&req))fail("interface_MAC");memcpy(link->mac,req.ifr_hwaddr.sa_data,6);
    if(ioctl(link->fd,SIOCGIFFLAGS,&req))fail("interface_flags");req.ifr_flags|=IFF_UP;
    if(ioctl(link->fd,SIOCSIFFLAGS,&req))fail("interface_up");
    int ignore=1;if(setsockopt(link->fd,SOL_PACKET,PACKET_IGNORE_OUTGOING,&ignore,sizeof(ignore)))fail("ignore_outgoing");
    struct sockaddr_ll address;memset(&address,0,sizeof(address));address.sll_family=AF_PACKET;address.sll_protocol=network16(TYPE);address.sll_ifindex=link->index;
    if(bind(link->fd,(struct sockaddr*)&address,sizeof(address)))fail("packet_bind");
    printf("XNS_EVENT {\"node\":\"%c\",\"event\":\"packet_probe\",\"available\":true,\"interface\":\"%s\"}\n",role,name);
}
static void transmit(struct link *link,const uint8_t *body,size_t length) {
    uint8_t frame[14+HEADER+MAX_PAYLOAD];memcpy(frame,link->peer,6);memcpy(frame+6,link->mac,6);put16(frame+12,TYPE);memcpy(frame+14,body,length);
    struct sockaddr_ll to;memset(&to,0,sizeof(to));to.sll_family=AF_PACKET;to.sll_ifindex=link->index;to.sll_halen=6;memcpy(to.sll_addr,link->peer,6);
    if(sendto(link->fd,frame,length+14,0,(struct sockaddr*)&to,sizeof(to))!=(ssize_t)(length+14))fail("frame_send");
}
static ssize_t receive(struct link *link,uint8_t *body,int timeout) {
    struct pollfd fd={link->fd,POLLIN,0};int ready=poll(&fd,1,timeout);if(ready<0)fail("poll");if(!ready)return 0;
    uint8_t frame[2048];ssize_t n=recv(link->fd,frame,sizeof(frame),0);if(n<14 || get16(frame+12)!=TYPE)return 0;
    if(!valid(frame+14,(size_t)n-14))return 0;
    size_t length=HEADER+get16(frame+14+20);memcpy(body,frame+14,length);
    uint32_t source=get32(body+12);if(source<1 || source>3 || source==role_id())return 0;
    if(body[5]==HELLO) {
        if(peer_known[source] && memcmp(peer_ids[source],body+28,32))return 0;
        memcpy(peer_ids[source],body+28,32);peer_known[source]=1;
    } else if(!peer_known[source] || memcmp(peer_ids[source],body+28,32))return 0;
    return (ssize_t)length;
}
static void hello(struct link *link) { uint8_t body[HEADER+MAX_PAYLOAD];size_t length=encode(body,HELLO,3,0,role_id(),0,"HELLO");if(!length)fail("hello_signature");transmit(link,body,length); }
static void endpoint_a(struct link *link) {
    uint8_t body[HEADER+MAX_PAYLOAD],incoming[HEADER+MAX_PAYLOAD];int complete=0;
    double deadline=seconds()+30;
    while(!peer_known[2] || !peer_known[3]) { if(seconds()>deadline)fail("hello_timeout");hello(link);receive(link,incoming,500); }
    for(uint32_t seq=1;seq<=CASES;seq++) {
        uint8_t task[1024],digest[32];for(size_t i=0;i<sizeof(task);i++)task[i]=(uint8_t)(seq*31+i*17);
        SHA256(task,sizeof(task),digest);char expected[65];hex(digest,32,expected);
        size_t length=encode_bytes(body,TASK,3,seq,1,2,task,sizeof(task));if(!length)fail("task_signature");int received=0;
        double start=seconds();
        for(int attempt=0;attempt<3 && !received;attempt++) {
            transmit(link,body,length);
            /* One deliberate repeat tests the receiver's in-memory deduplication. */
            if(seq==1 && attempt==0)transmit(link,body,length);
            double until=seconds()+4;
            while(seconds()<until && !received) {
                ssize_t n=receive(link,incoming,250);if(!n)continue;
                if(incoming[5]!=RESULT || get32(incoming+8)!=seq || get32(incoming+12)!=2 || get32(incoming+16)!=1)continue;
                char text[MAX_PAYLOAD+1];size_t size=get16(incoming+20);memcpy(text,incoming+HEADER,size);text[size]=0;
                if(strcmp(text,expected) || memcmp(incoming+60,node_id,32))fail("incorrect_task_result");
                received=1;complete++;
                printf("XNS_EVENT {\"node\":\"A\",\"event\":\"task_result\",\"sequence\":%u,\"sha256\":\"%s\",\"round_trip_ms\":%.3f}\n",seq,expected,(seconds()-start)*1000);
            }
        }
        if(!received)fail("task_timeout");
    }
    printf("XNS_EVENT {\"node\":\"A\",\"event\":\"summary\",\"completed\":%d,\"expected\":%d,\"ok\":true,\"llm\":false}\n",complete,CASES);
    sleep(1);reboot(RB_AUTOBOOT);for(;;)pause();
}
static void endpoint_b(struct link *link) {
    uint8_t body[HEADER+MAX_PAYLOAD],out[HEADER+MAX_PAYLOAD];int seen[CASES+1]={0};char cached[CASES+1][65];int executions=0;double next_hello=0;
    for(;;) {
        if(seconds()>=next_hello){hello(link);next_hello=seconds()+1;}
        ssize_t n=receive(link,body,1000);if(!n || body[5]!=TASK || get32(body+12)!=1 || get32(body+16)!=2)continue;
        uint32_t seq=get32(body+8);if(seq<1 || seq>CASES)continue;
        size_t size=get16(body+20);if(size!=1024 || memcmp(body+60,node_id,32))fail("task_format");
        for(size_t i=0;i<size;i++)if(body[HEADER+i]!=(uint8_t)(seq*31+i*17))fail("task_payload");
        if(!seen[seq]){uint8_t digest[32];SHA256(body+HEADER,size,digest);hex(digest,32,cached[seq]);seen[seq]=1;executions++;}
        else printf("XNS_EVENT {\"node\":\"B\",\"event\":\"duplicate\",\"sequence\":%u}\n",seq);
        size_t length=encode(out,RESULT,3,seq,2,1,cached[seq]);if(!length)fail("result_signature");transmit(link,out,length);
        printf("XNS_EVENT {\"node\":\"B\",\"event\":\"receipt\",\"sequence\":%u,\"sha256\":\"%s\",\"executions\":%d}\n",seq,cached[seq],executions);
    }
}
static void relay(struct link *left,struct link *right) {
    struct link *links[]={left,right};uint8_t body[HEADER+MAX_PAYLOAD];double next_hello=0;
    for(;;)for(int i=0;i<2;i++) {
        if(seconds()>=next_hello){hello(left);hello(right);next_hello=seconds()+1;}
        ssize_t n=receive(links[i],body,50);if(!n)continue;
        uint32_t dst=get32(body+16);int outgoing=body[5]==HELLO?1-i:dst==1?0:dst==2?1:-1;
        if(outgoing<0 || outgoing==i || body[6]<=1)continue;
        body[6]--;put32(body+24,checksum(body,(size_t)n));transmit(links[outgoing],body,(size_t)n);
        printf("XNS_EVENT {\"node\":\"R\",\"event\":\"forward\",\"sequence\":%u,\"kind\":%u,\"incoming\":\"%s\",\"outgoing\":\"%s\",\"hop_limit\":%u}\n",get32(body+8),body[5],links[i]->name,links[outgoing]->name,body[6]);
    }
}
static int guest(void) {
    setvbuf(stdout,NULL,_IONBF,0);
    if(getpid()!=1){fputs("Live guest execution requires PID 1 in the isolated initramfs\n",stderr);return 2;}
    if(mount("proc","/proc","proc",0,NULL) || mount("sysfs","/sys","sysfs",0,NULL) || mount("devtmpfs","/dev","devtmpfs",0,NULL))fail("mounts");
    FILE *cmd=fopen("/proc/cmdline","r");char args[2048]={0};if(!cmd || !fgets(args,sizeof(args),cmd))fail("cmdline");fclose(cmd);
    char *which=strstr(args,"xns.role=");if(!which)fail("missing_role");role=which[9];if(role!='A' && role!='B' && role!='R')fail("unknown_role");
    if(!keygen())fail("key_generation");char pub[65],id[65];hex(public_key,32,pub);hex(node_id,32,id);
    printf("XNS_EVENT {\"node\":\"%c\",\"event\":\"boot\",\"protocol\":\"XNS1-Ed25519-TOFU-smoke\",\"node_id\":\"%s\",\"public_key\":\"%s\"}\n",role,id,pub);probe();
    const uint8_t a[]={2,88,0,0,0,1},b[]={2,88,0,0,0,2},rl[]={2,88,0,0,0,17},rr[]={2,88,0,0,0,18};
    struct link left,right;
    if(role=='A'){openlink(&left,"eth0",rl);sleep(3);endpoint_a(&left);}
    if(role=='B'){openlink(&left,"eth0",rr);endpoint_b(&left);}
    openlink(&left,"eth0",a);openlink(&right,"eth1",b);relay(&left,&right);return 0;
}
#endif

int main(int argc,char **argv) {
    if(argc==2 && !strcmp(argv[1],"--selftest"))return selftest();
#ifdef __linux__
    return guest();
#else
    fputs("Guest mode requires Linux; only --selftest is portable\n",stderr);return 2;
#endif
}
