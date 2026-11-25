// Mesh Command V1.4 for the ESP32 "Cheap Yellow Display" (ESP32-2432S028R) — part of Radio Gremlin
// Copyright (C) 2026 Bad Audio Guy
// SPDX-License-Identifier: GPL-3.0-only
//
// Touchscreen monitor for the Radio Gremlin Mesh Command API: live radio activity, node directory,
// packet/traffic view and system status. It only reads from the API (HTTP GET); it never transmits.
//
// Before building:
//   1. Copy secrets.example.h to secrets.h and set your Wi-Fi and the Mesh Command API address.
//   2. Configure TFT_eSPI for the CYD (see firmware/README.md).
// Libraries: TFT_eSPI, XPT2046_Touchscreen, ArduinoJson (v7), plus the ESP32 Arduino core.
//
// This program is free software: you can redistribute it and/or modify it under the terms of the GNU
// General Public License version 3. It is distributed WITHOUT ANY WARRANTY. See LICENSE.

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <SPI.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <Preferences.h>
#include <math.h>
#include <vector>

#include "secrets.h"   // copy secrets.example.h to secrets.h and edit it (secrets.h is git-ignored)
const char* ssid=WIFI_SSID;
const char* password=WIFI_PASSWORD;
const char* server=MESH_COMMAND_URL;
TFT_eSPI tft;
TFT_eSprite s(&tft);
SPIClass touchSPI(VSPI);
XPT2046_Touchscreen ts(33,36);
Preferences prefs;
uint16_t bg,panel,amber,olive,green,red,dim,blue,yellow;
JsonDocument statusDoc, nodesDoc;
bool online=false, nodesOK=false, held=false, swapAxes=false;
float xl,xr,yt,yb;
unsigned long lastPoll=0,lastNodes=0,lastGood=0,lastDraw=0,lastRetry=0,flash=0;
unsigned long previousRF=0;
bool haveStatus=false, rxFlash=false;
int page=0, offset=0;
String selected="";

void releaseTouch(){while(ts.touched()) delay(20); delay(150);}
void calibrate(){
  const int X[]={25,295,295,25},Y[]={25,25,215,215};
  float a[4],b[4];
  do {
    releaseTouch();
    for(int i=0;i<4;i++){
      tft.fillScreen(TFT_BLACK); tft.setTextDatum(MC_DATUM); tft.setTextColor(TFT_YELLOW,TFT_BLACK);
      tft.drawString("TOUCH CALIBRATION",160,100,2);
      tft.drawString("Touch and hold target",160,125,2);
      tft.drawString(String(i+1)+" OF 4",160,150,2);
      tft.drawCircle(X[i],Y[i],12,TFT_YELLOW);
      tft.drawFastHLine(X[i]-16,Y[i],33,TFT_YELLOW); tft.drawFastVLine(X[i],Y[i]-16,33,TFT_YELLOW);
      float u=0,v=0; int n=0;
      while(n<15){if(ts.touched()){TS_Point p=ts.getPoint(); if(p.z>100){u+=p.x;v+=p.y;n++;}}else{u=v=0;n=0;}delay(20);}
      a[i]=u/n;b[i]=v/n;tft.fillCircle(X[i],Y[i],8,TFT_GREEN);releaseTouch();
    }
    swapAxes=fabs(b[1]+b[2]-b[0]-b[3])>fabs(a[1]+a[2]-a[0]-a[3]);
    float *x=swapAxes?b:a,*y=swapAxes?a:b;
    xl=(x[0]+x[3])/2;xr=(x[1]+x[2])/2;yt=(y[0]+y[1])/2;yb=(y[2]+y[3])/2;
  }while(fabs(xr-xl)<1000||fabs(yb-yt)<1000);
  prefs.begin("meshcmd",false);prefs.putBool("swap",swapAxes);prefs.putFloat("xl",xl);prefs.putFloat("xr",xr);prefs.putFloat("yt",yt);prefs.putFloat("yb",yb);prefs.putBool("valid",true);prefs.end();
}
void loadCalibration(){prefs.begin("meshcmd",true);bool valid=prefs.getBool("valid",false);swapAxes=prefs.getBool("swap",false);xl=prefs.getFloat("xl",200);xr=prefs.getFloat("xr",3800);yt=prefs.getFloat("yt",200);yb=prefs.getFloat("yb",3800);prefs.end();if(!valid||fabs(xr-xl)<1000||fabs(yb-yt)<1000)calibrate();}
bool touch(int &x,int &y){if(!ts.touched()){held=false;return false;}if(held)return false;TS_Point p=ts.getPoint();if(p.z<100)return false;held=true;float a=swapAxes?p.y:p.x,b=swapAxes?p.x:p.y;x=constrain((int)round(25+(a-xl)*270/(xr-xl)),0,319);y=constrain((int)round(25+(b-yt)*190/(yb-yt)),0,239);return true;}
void txt(String v,int x,int y,uint16_t c,int datum=TL_DATUM,int font=2){s.setTextDatum(datum);s.setTextColor(c);s.drawString(v,x,y,font);}
String fit(String v,int w){while(v.length()&&s.textWidth(v,2)>w)v.remove(v.length()-1);return v;}
String val(JsonVariantConst v){return v.isNull()?String("---"):v.as<String>();}
String age(JsonVariantConst v,unsigned long extra=0){if(v.isNull())return "---";unsigned long a=v.as<unsigned long>()+extra;if(a<60)return String(a)+"s";if(a<3600)return String(a/60)+"m";if(a<86400)return String(a/3600)+"h";return String(a/86400)+"d";}
String uptime(unsigned long a){char b[24];snprintf(b,sizeof(b),"%02lu:%02lu:%02lu",a/3600,a/60%60,a%60);return b;}
void button(int x,int y,int w,int h,String label,bool active=false){s.fillRoundRect(x,y,w,h,4,active?olive:panel);s.drawRoundRect(x,y,w,h,4,amber);txt(label,x+w/2,y+h/2,active?TFT_BLACK:amber,MC_DATUM);}
void stat(int x,String label,String value){s.fillRoundRect(x,49,98,55,4,panel);s.drawRoundRect(x,49,98,55,4,olive);txt(label,x+49,61,amber,MC_DATUM);txt(value,x+49,84,amber,MC_DATUM,value.length()>5?2:4);}
void bar(int y,int n){for(int i=0;i<20;i++)s.fillRoundRect(10+i*15,y,12,10,2,i>=n?dim:i<5?red:i<10?amber:green);}
void row(String label,String value,int y){txt(label,10,y,amber);txt(fit(value,190),309,y,TFT_WHITE,TR_DATUM);s.drawFastHLine(10,y+18,300,dim);}
uint16_t routeColor(JsonVariantConst e){
  String r=val(e["route"]);
  if(r=="DIRECT")return green;
  if(r=="RELAYED")return yellow;
  if(r=="MQTT"||r=="GATEWAY")return blue;
  return TFT_LIGHTGREY;
}
String routeLabel(JsonVariantConst e){
  String r=val(e["route"]);
  if(r=="RELAYED")return val(e["hops"])+" HOP"+(e["hops"].as<int>()==1?"":"S");
  if(r=="DIRECT"||r=="MQTT"||r=="GATEWAY")return r;
  return r=="RF UNKNOWN"?"RF ?":"UNKNOWN";
}
void monitor(){
  stat(8,"NODES",val(statusDoc["nodes"]));stat(111,"DIRECT",val(statusDoc["direct_packets"]));stat(214,"RELAYED",val(statusDoc["relayed_packets"]));
  bool r=!statusDoc["rssi"].isNull(), q=!statusDoc["snr"].isNull();int rssi=statusDoc["rssi"]|0;float snr=statusDoc["snr"]|0.0f;
  txt("RSSI",10,111,amber);txt(r?String(rssi)+" dBm":"--- dBm",309,111,amber,TR_DATUM);bar(130,r?constrain(map(rssi,-130,-30,0,20),0L,20L):0);
  txt("SNR",10,146,amber);txt(q?String(snr,1)+" dB":"--- dB",309,146,amber,TR_DATUM);bar(165,q?constrain(map((int)(snr*10),-200,100,0,20),0L,20L):0);
  txt("LAST RF: "+fit(val(statusDoc["last_rf_sender"]),125),10,182,amber);txt(age(statusDoc["rf_age"],(millis()-lastGood)/1000)+" AGO",309,182,amber,TR_DATUM);
}
void systemPage(){
  row("WIFI",WiFi.status()==WL_CONNECTED?"CONNECTED":"DISCONNECTED",49);
  row("CYD IP",WiFi.localIP().toString(),69);
  row("API UPTIME",haveStatus?uptime(statusDoc["uptime"]|0UL):"---",89);
  row("TOTAL / RF",val(statusDoc["packets"])+" / "+val(statusDoc["rf_packets"]),109);
  row("RF UNKNOWN / OTHER",val(statusDoc["unknown_rf_packets"])+" / "+val(statusDoc["other_packets"]),129);
  row("SERVER",String(server).substring(String(server).indexOf("//")+2),149);
  button(70,170,180,28,"CALIBRATE TOUCH");
}
JsonObjectConst findNode(){for(JsonObjectConst n:nodesDoc["nodes"].as<JsonArrayConst>())if(val(n["id"])==selected)return n;return JsonObjectConst();}
void directory(){
  JsonArrayConst a=nodesDoc["nodes"].as<JsonArrayConst>();int count=a.size();offset=constrain(offset,0,count?((count-1)/5)*5:0);
  txt("NODE",10,49,amber);txt("RSSI",116,49,amber);txt("HOPS",185,49,amber);txt("AGE",309,49,amber,TR_DATUM);
  for(int i=0;i<5&&offset+i<count;i++){JsonObjectConst n=a[offset+i];int y=66+i*21;bool local=n["local"]|false;s.fillRect(8,y,304,20,i%2?bg:panel);txt(fit(val(n["short_name"]),100),12,y+2,amber);txt(local?"BASE":val(n["rssi"]),116,y+2,TFT_WHITE);txt(val(n["hops_away"]),185,y+2,TFT_WHITE);txt(local?"LOCAL":age(n["age"],(millis()-lastNodes)/1000),309,y+2,TFT_WHITE,TR_DATUM);}
  if(!nodesOK)txt("NODE API OFFLINE / STALE",160,118,red,MC_DATUM);
  button(8,175,65,24,"< PREV");button(247,175,65,24,"NEXT >");txt(String(count?offset/5+1:0)+" / "+String((count+4)/5),160,187,amber,MC_DATUM);
}
void details(){JsonObjectConst n=findNode();if(n.isNull()){txt("NODE UNAVAILABLE",160,100,red,MC_DATUM);button(8,175,75,24,"BACK");return;}
  txt(fit(val(n["long_name"]),300),10,48,amber);txt(fit(val(n["hardware"])+" / "+val(n["role"]),300),10,66,TFT_WHITE);
  bool local=n["local"]|false;txt("ID: "+val(n["id"]),10,84,amber);txt("HOPS: "+val(n["hops_away"]),309,84,amber,TR_DATUM);
  txt("HEARD: "+(local?String("LOCAL"):age(n["age"],(millis()-lastNodes)/1000)),10,102,amber);txt("RF: "+age(n["rf_age"],(millis()-lastNodes)/1000),309,102,amber,TR_DATUM);
  txt("DIRECT RSSI: "+val(n["rssi"]),10,120,TFT_WHITE);txt("SNR: "+val(n["snr"]),309,120,TFT_WHITE,TR_DATUM);
  int b=n["battery"]|-1;float v=n["voltage"]|0.0f;String battery=b==101?"EXT POWER":b>=0&&b<=100?String(b)+"%":"---";
  txt("BAT: "+battery,10,138,amber);txt(v>0?String(v,2)+" V":"--- V",309,138,amber,TR_DATUM);
  txt("Reported SNR: "+val(n["reported_snr"]),10,156,TFT_WHITE);button(8,175,75,24,"BACK");if(!nodesOK)txt("STALE",309,187,red,MR_DATUM);
}
JsonDocument trafficDoc;
bool trafficOK=false, paused=false;
int trafficFilter=0, trafficOffset=0;
unsigned long lastTraffic=0;
JsonDocument eventDetail;
bool eventOpen=false;
int eventCount(){int n=0;for(JsonObjectConst e:trafficDoc["events"].as<JsonArrayConst>())if(trafficFilter==0||(trafficFilter==1&&(e["text"]|false))||(trafficFilter==2&&(e["rf"]|false)))n++;return n;}
JsonObjectConst eventAt(int index){for(JsonObjectConst e:trafficDoc["events"].as<JsonArrayConst>()){if(trafficFilter==1&&!(e["text"]|false))continue;if(trafficFilter==2&&!(e["rf"]|false))continue;if(index--==0)return e;}return JsonObjectConst();}
void trafficPage(){
 if(eventOpen){JsonObjectConst e=eventDetail.as<JsonObjectConst>();
 txt(val(e["time"]),10,49,TFT_WHITE);txt(fit(val(e["sender"]),190),309,49,amber,TR_DATUM);
 txt(fit(val(e["type"]),300),10,67,TFT_WHITE);
 txt(routeLabel(e),10,85,routeColor(e));txt("Relay: "+val(e["relay"]),309,85,TFT_WHITE,TR_DATUM);
 txt("RSSI: "+val(e["rssi"]),10,103,TFT_WHITE);txt("SNR: "+val(e["snr"]),309,103,TFT_WHITE,TR_DATUM);
 txt("Hops left: "+val(e["hop_limit"])+" / "+val(e["hop_start"]),10,121,amber);
 txt(fit(val(e["transport"]),300),10,139,routeColor(e));
 String msg=val(e["summary"]);for(int i=0;i<2&&msg.length();i++){String part=fit(msg,300);if(!part.length())break;txt(part,10,154+i*13,TFT_WHITE);msg.remove(0,part.length());}button(8,180,75,20,"BACK");return;}
 button(8,49,70,23,"ALL",trafficFilter==0);button(86,49,70,23,"TEXT",trafficFilter==1);button(164,49,70,23,"RF",trafficFilter==2);button(242,49,70,23,paused?"RESUME":"PAUSE",paused);
 int count=eventCount();trafficOffset=constrain(trafficOffset,0,count?((count-1)/3)*3:0);
 for(int i=0;i<3;i++){JsonObjectConst e=eventAt(trafficOffset+i);if(e.isNull())break;int y=77+i*31;s.fillRect(8,y,304,29,i%2?bg:panel);txt(val(e["time"]),12,y,TFT_WHITE);txt(fit(val(e["sender"]),105),82,y,green);txt(val(e["rssi"]),307,y,amber,TR_DATUM);txt(fit(val(e["summary"]),190),12,y+14,amber);txt(routeLabel(e),307,y+14,routeColor(e),TR_DATUM);}
 if(!count)txt("NO MATCHING EVENTS",160,120,amber,MC_DATUM);
 txt(!trafficOK?"STALE":paused?"PAUSED":"LIVE",160,174,!trafficOK?red:green,MC_DATUM);
 button(8,181,70,19,"NEWER");button(242,181,70,19,"OLDER");txt(String(count?trafficOffset+1:0)+"-"+String(min(count,trafficOffset+3))+" / "+String(count),160,190,amber,MC_DATUM);
}
void draw(){s.fillSprite(bg);s.drawRoundRect(2,2,316,236,5,olive);txt("MESH COMMAND V1.4",10,6,amber);s.fillCircle(304,14,5,rxFlash?green:dim);s.drawFastHLine(8,26,304,olive);txt(page==1?"NODE DIRECTORY":page==3?"LIVE TRAFFIC":"RADIO GREMLIN",10,30,amber);txt(online?"API ONLINE":"API OFFLINE",309,30,online?green:red,TR_DATUM);if(page==0)monitor();else if(page==2)systemPage();else if(page==3)trafficPage();else if(selected.length())details();else directory();button(8,204,73,28,"MON",page==0);button(85,204,73,28,"NODES",page==1);button(162,204,73,28,"TRAFFIC",page==3);button(239,204,73,28,"SYS",page==2);s.pushSprite(0,0);}
bool fetch(const char* path,JsonDocument &dest){if(WiFi.status()!=WL_CONNECTED)return false;HTTPClient h;h.setConnectTimeout(1000);h.setTimeout(1500);if(!h.begin(String(server)+path))return false;int code=h.GET();bool ok=false;if(code==200){JsonDocument tmp;DeserializationError e=deserializeJson(tmp,h.getString());if(!e){dest=std::move(tmp);ok=true;}}h.end();return ok;}
void pollStatus(){online=fetch("/status",statusDoc)&&(statusDoc["api_online"]|false);if(online){unsigned long n=statusDoc["rf_packets"]|0UL;if(haveStatus&&n>previousRF){rxFlash=true;flash=millis();}previousRF=n;haveStatus=true;lastGood=millis();}}
void pollNodes(){nodesOK=fetch("/nodes",nodesDoc)&&nodesDoc["nodes"].is<JsonArray>();if(nodesOK)lastNodes=millis();}
void pollTraffic(){lastTraffic=millis();if(paused||eventOpen||trafficOffset>0)return;trafficOK=fetch("/traffic",trafficDoc)&&trafficDoc["events"].is<JsonArray>();}
void handleTouch(){int x,y;if(!touch(x,y))return;if(y>=204){page=x<83?0:x<160?1:x<237?3:2;selected="";eventOpen=false;if(page==1)pollNodes();if(page==3)pollTraffic();}else if(page==3){if(eventOpen){if(y>=180&&y<201&&x<85)eventOpen=false;}else if(y>=49&&y<73){if(x>=240){paused=!paused;if(!paused){trafficOffset=0;pollTraffic();}}else{trafficFilter=x<82?0:x<160?1:2;trafficOffset=0;}}else if(y>=77&&y<170){JsonObjectConst e=eventAt(trafficOffset+(y-77)/31);if(!e.isNull()){eventDetail.set(e);eventOpen=true;}}else if(y>=181&&y<201){if(x<82){trafficOffset=max(0,trafficOffset-3);}else if(x>=240&&trafficOffset+3<eventCount())trafficOffset+=3;}}else if(page==2&&y>=170&&y<=198&&x>=70&&x<=250){releaseTouch();calibrate();held=false;}else if(page==1){if(selected.length()){if(y>=175&&y<200&&x<90)selected="";}else if(y>=175&&y<200){int count=nodesDoc["nodes"].size();if(x<80)offset=max(0,offset-5);else if(x>240&&offset+5<count)offset+=5;}else if(y>=66&&y<171){int i=offset+(y-66)/21;JsonArrayConst a=nodesDoc["nodes"].as<JsonArrayConst>();if(i<(int)a.size())selected=val(a[i]["id"]);}}draw();}
void setup(){Serial.begin(115200);pinMode(21,OUTPUT);digitalWrite(21,HIGH);tft.init();tft.setRotation(1);tft.invertDisplay(true);bg=tft.color565(5,10,5);panel=tft.color565(22,30,14);amber=tft.color565(255,180,35);olive=tft.color565(85,100,40);green=tft.color565(30,220,70);red=tft.color565(240,40,30);dim=tft.color565(35,45,25);blue=tft.color565(80,175,255);yellow=tft.color565(255,225,60);touchSPI.begin(25,39,32,33);ts.begin(touchSPI);ts.setRotation(1);loadCalibration();s.setColorDepth(8);if(!s.createSprite(320,240)){tft.fillScreen(TFT_BLACK);tft.setTextColor(TFT_RED);tft.drawString("SPRITE MEMORY ERROR",10,100,2);while(true)delay(1000);}WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.begin(ssid,password);draw();}
void loop(){handleTouch();unsigned long now=millis();if(WiFi.status()!=WL_CONNECTED){online=false;nodesOK=false;trafficOK=false;if(now-lastRetry>=10000){lastRetry=now;WiFi.reconnect();}}if(now-lastPoll>=2000){lastPoll=now;pollStatus();if(page==1&&now-lastNodes>=5000)pollNodes();if(page==3&&now-lastTraffic>=3000)pollTraffic();draw();lastDraw=millis();}if(rxFlash&&millis()-flash>=600){rxFlash=false;draw();}if(millis()-lastDraw>=1000){lastDraw=millis();draw();}delay(10);}
