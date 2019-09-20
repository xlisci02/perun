#include <assert.h>
#include <stdio.h>
#include <unistd.h>

#define REPS 100
#define SLEEP_TIME 1000

int main(int argc, char ** argv){
	FILE * fp = fopen(argv[1],"r");
	int num, i;
	fscanf(fp,"%d ",&num);
	if( num != 5 ){
		for(i = 0; i < REPS; i++)
			usleep(SLEEP_TIME);
	}
	return 0;
}
